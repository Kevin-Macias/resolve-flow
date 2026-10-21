import { sessionHeaders, sessionEnded } from '../api/browser-client'
import {
  acceptSnapshot,
  decodeEvent,
  validateRunId,
  type CustomerSnapshot,
  type Progress,
} from './contract'
import { ProtocolError, SseParser } from './parser'

export const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 10000] as const
export const HEALTHY_RESET_MS = 30_000
export const READ_TIMEOUT_MS = 45_000
export type ConnectionState =
  | 'connecting'
  | 'live'
  | 'reconnecting'
  | 'ended'
  | 'unavailable'
  | 'access_lost'
  | 'protocol_error'
export type StreamOptions = {
  url: string
  token: string
  runId: string
  signal?: AbortSignal
  initialSnapshot?: CustomerSnapshot
  onSnapshot: (snapshot: CustomerSnapshot) => void
  onState: (state: ConnectionState) => void
  onEnd: (reason: Exclude<Progress, 'processing'>) => void
  fetcher?: typeof fetch
}
class AccessLost extends Error {}
class Unavailable extends Error {}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason)
      return
    }
    const abort = () => {
      clearTimeout(timer)
      reject(signal.reason)
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort)
      resolve()
    }, ms)
    signal.addEventListener('abort', abort, { once: true })
  })
}

/** Start a read-only subscription. Stop aborts fetch, body reads, and retry timers.
 * Reopen explicitly after a successful answer operation, or manual reconnect;
 * initialSnapshot preserves the last cursor for that same run.
 */
export function startCustomerStream(options: StreamOptions) {
  validateRunId(options.runId)
  let previous = options.initialSnapshot
  if (previous) {
    decodeEvent(
      {
        event: 'snapshot',
        id: `${previous.run_id}:${previous.revision}`,
        data: JSON.stringify(previous),
      },
      options.runId,
    )
  }
  const controller = new AbortController()
  const signal = options.signal
    ? AbortSignal.any([options.signal, controller.signal])
    : controller.signal
  const emitState = (state: ConnectionState) => {
    if (!signal.aborted) options.onState(state)
  }

  async function run() {
    let retries = 0
    while (!signal.aborted) {
      emitState(retries ? 'reconnecting' : 'connecting')
      if (signal.aborted) return
      const attempt = new AbortController()
      const attemptSignal = AbortSignal.any([signal, attempt.signal])
      let timeout: ReturnType<typeof setTimeout> | undefined
      const armTimeout = () => {
        clearTimeout(timeout)
        timeout = setTimeout(() => attempt.abort(), READ_TIMEOUT_MS)
      }
      let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
      try {
        armTimeout()
        const headers: Record<string, string> = {
          Accept: 'text/event-stream',
          ...sessionHeaders(options.token),
        }
        if (previous)
          headers['Last-Event-ID'] = `${options.runId}:${previous.revision}`
        const response = await (options.fetcher ?? fetch)(options.url, {
          method: 'GET',
          headers,
          signal: attemptSignal,
          cache: 'no-store',
        })
        if (signal.aborted) return
        sessionEnded(options.token, response.status)
        if ([401, 403, 404].includes(response.status)) throw new AccessLost()
        if (!response.ok) {
          if (response.status >= 500 || response.status === 429)
            throw new Unavailable()
          throw new ProtocolError('Rejected cursor or request')
        }
        if (
          response.headers.get('content-type')?.split(';')[0].trim() !==
            'text/event-stream' ||
          !response.body
        ) {
          throw new ProtocolError('Invalid stream response')
        }
        reader = response.body.getReader()
        const decoder = new TextDecoder('utf-8', { fatal: true })
        const parser = new SseParser()
        const healthySince = Date.now()
        let connectionSnapshot: CustomerSnapshot | undefined
        while (!signal.aborted) {
          armTimeout()
          const part = await reader.read()
          if (signal.aborted) return
          // EOF may truncate a UTF-8 character or frame; retain the last complete snapshot.
          if (part.done) throw new Unavailable()
          let decoded: string
          try {
            decoded = decoder.decode(part.value, { stream: true })
          } catch {
            throw new ProtocolError('Invalid UTF-8')
          }
          for (const frame of parser.push(decoded)) {
            if (signal.aborted) return
            const event = decodeEvent(frame, options.runId)
            if (event.kind === 'snapshot') {
              const changed = acceptSnapshot(previous, event.snapshot)
              connectionSnapshot = event.snapshot
              if (changed) {
                previous = event.snapshot
                retries = 0
                options.onSnapshot(event.snapshot)
              }
              emitState('live')
            } else if (event.kind === 'stream_end') {
              if (
                !connectionSnapshot ||
                connectionSnapshot.progress !== event.reason
              ) {
                throw new ProtocolError('End without matching final snapshot')
              }
              emitState('ended')
              if (!signal.aborted) options.onEnd(event.reason)
              return
            } else {
              if (event.reason === 'access_lost') throw new AccessLost()
              throw new Unavailable()
            }
          }
          if (Date.now() - healthySince >= HEALTHY_RESET_MS) retries = 0
        }
      } catch (error) {
        if (signal.aborted) return
        if (error instanceof AccessLost) {
          emitState('access_lost')
          return
        }
        if (error instanceof ProtocolError) {
          emitState('protocol_error')
          return
        }
      } finally {
        clearTimeout(timeout)
        attempt.abort()
        if (reader) {
          try {
            await reader.cancel()
          } catch {
            /* aborted network */
          }
          reader.releaseLock()
        }
      }
      if (signal.aborted) return
      const wait = RETRY_DELAYS_MS[retries]
      if (wait === undefined) {
        emitState('unavailable')
        return
      }
      retries++
      emitState('reconnecting')
      try {
        await delay(wait, signal)
      } catch {
        return
      }
    }
  }
  return { stop: () => controller.abort(), done: run() }
}
