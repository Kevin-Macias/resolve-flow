import fixture from './customer-snapshot.fixture.sse?raw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { acceptSnapshot, decodeEvent, type CustomerSnapshot } from './contract'
import { READ_TIMEOUT_MS, startCustomerStream } from './client'
import { MAX_FRAME_CHARS, ProtocolError, SseParser } from './parser'

const runId = '11111111-1111-1111-1111-111111111111'
const snapshot = (
  revision = 1,
  progress: CustomerSnapshot['progress'] = 'processing',
): CustomerSnapshot => ({
  version: 1,
  run_id: runId,
  revision,
  progress,
  customer_update: null,
})
const wire = (value = snapshot()) =>
  `id: ${runId}:${value.revision}\nevent: snapshot\ndata: ${JSON.stringify(value)}\n\n`
const end = (reason = 'waiting_input') =>
  `event: stream_end\ndata: ${JSON.stringify({ version: 1, reason })}\n\n`
function response(text: string) {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(text))
        controller.close()
      },
    }),
    {
      headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
    },
  )
}
function setup(fetcher: typeof fetch, initialSnapshot?: CustomerSnapshot) {
  const onSnapshot = vi.fn<(snapshot: CustomerSnapshot) => void>()
  const onState = vi.fn()
  const onEnd = vi.fn()
  const stream = startCustomerStream({
    url: 'http://test/stream',
    token: 'secret',
    runId,
    fetcher,
    initialSnapshot,
    onSnapshot,
    onState,
    onEnd,
  })
  return { ...stream, onSnapshot, onState, onEnd }
}
afterEach(() => {
  vi.useRealTimers()
})

describe('framing and closed projections', () => {
  it('round trips split UTF-8, CRLF, comments and multiline data at every byte boundary', () => {
    const value = { ...snapshot(), customer_update: 'café 🐈\nquestion' }
    const text = `: heartbeat\r\n\r\nid: ${runId}:1\r\nevent: snapshot\r\ndata: {\r\ndata: ${JSON.stringify(value).slice(1)}\r\n\r\n`
    const bytes = new TextEncoder().encode(text)
    for (let split = 0; split <= bytes.length; split++) {
      const parser = new SseParser()
      const decoder = new TextDecoder('utf-8', { fatal: true })
      const frames = [
        ...parser.push(decoder.decode(bytes.slice(0, split), { stream: true })),
        ...parser.push(decoder.decode(bytes.slice(split))),
      ]
      expect(frames).toHaveLength(1)
      expect(decodeEvent(frames[0], runId)).toEqual({
        kind: 'snapshot',
        id: `${runId}:1`,
        snapshot: value,
      })
    }
  })
  it('discards incomplete frames and bounds unterminated frames', () => {
    expect(new SseParser().push(wire().slice(0, -1))).toEqual([])
    expect(() => new SseParser().push('x'.repeat(MAX_FRAME_CHARS + 1))).toThrow(
      ProtocolError,
    )
    expect(() => new SseParser().push('id: bad\0id\n\n')).toThrow(ProtocolError)
  })
  it.each([
    { ...snapshot(), revision: 0 },
    { ...snapshot(), revision: 1.5 },
    { ...snapshot(), revision: '1' },
    { ...snapshot(), revision: Number.MAX_SAFE_INTEGER + 1 },
    { ...snapshot(), run_id: 'another-run' },
    { ...snapshot(), version: 2 },
    { ...snapshot(), internal_evidence: 'private' },
    { ...snapshot(), progress: 'unknown' },
    { ...snapshot(), customer_update: 'a'.repeat(2001) },
    { ...snapshot(), customer_update: false },
  ])('rejects malformed or unallowlisted payloads %j', (value) => {
    expect(() =>
      decodeEvent(
        {
          event: 'snapshot',
          id: `${runId}:${value.revision}`,
          data: JSON.stringify(value),
        },
        runId,
      ),
    ).toThrow(ProtocolError)
  })
  it('accepts revision gaps, ignores identical duplicates, rejects conflicts and reversals', () => {
    expect(acceptSnapshot(snapshot(), snapshot(3))).toBe(true)
    expect(acceptSnapshot(snapshot(), snapshot())).toBe(false)
    expect(() => acceptSnapshot(snapshot(2), snapshot())).toThrow(ProtocolError)
    expect(() =>
      acceptSnapshot(snapshot(), {
        ...snapshot(),
        customer_update: 'different',
      }),
    ).toThrow(ProtocolError)
  })

  it.each([null, [], true, 1, 'snapshot'])(
    'rejects non-object JSON payloads %j',
    (value) => {
      expect(() =>
        decodeEvent({
          event: 'snapshot', id: `${runId}:1`, data: JSON.stringify(value),
        }, runId),
      ).toThrow(ProtocolError)
    },
  )

  it('counts snapshot text in Unicode code points and preserves it unchanged', () => {
    const value = { ...snapshot(), customer_update: '🐈'.repeat(2000) }
    const frame = {
      event: 'snapshot', id: `${runId}:1`, data: JSON.stringify(value),
    }
    expect(decodeEvent(frame, runId)).toEqual({
      kind: 'snapshot', id: frame.id, snapshot: value,
    })
    expect(() =>
      decodeEvent({
        ...frame,
        data: JSON.stringify({ ...value, customer_update: '🐈'.repeat(2001) }),
      }, runId),
    ).toThrow(ProtocolError)
  })

  it.each([
    { event: 'stream_end', data: { version: 1, reason: 'processing' } },
    { event: 'stream_end', data: { version: 2, reason: 'waiting_input' } },
    {
      event: 'stream_end',
      data: { version: 1, reason: 'waiting_input', internal: 'private' },
    },
    { event: 'stream_error', data: { version: 1, reason: 'unknown' } },
    {
      event: 'stream_error',
      data: { version: 1, reason: 'unavailable', internal: 'private' },
    },
  ])('rejects invalid control payloads %j', ({ event, data }) => {
    expect(() => decodeEvent({ event, data: JSON.stringify(data) }, runId)).toThrow(
      ProtocolError,
    )
  })

  it('rejects cursor changes on control events and mismatched snapshot cursors', () => {
    for (const frame of [
      { event: 'snapshot', id: `${runId}:2`, data: JSON.stringify(snapshot()) },
      {
        event: 'stream_end', id: `${runId}:1`,
        data: JSON.stringify({ version: 1, reason: 'waiting_input' }),
      },
      {
        event: 'stream_error', id: '',
        data: JSON.stringify({ version: 1, reason: 'unavailable' }),
      },
    ]) {
      expect(() => decodeEvent(frame, runId)).toThrow(ProtocolError)
    }
  })
})

describe('read-only connection lifecycle', () => {
  it.each(['waiting_input', 'stage_finished', 'stage_failed'] as const)(
    'stops after final %s snapshot then end',
    async (reason) => {
      const fetcher = vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(
          response(wire(snapshot(1, reason)) + end(reason)),
        )
      const stream = setup(fetcher)
      await stream.done
      expect(stream.onSnapshot).toHaveBeenCalledOnce()
      expect(stream.onEnd).toHaveBeenCalledWith(reason)
      expect(stream.onState).toHaveBeenLastCalledWith('ended')
      expect(fetcher).toHaveBeenCalledOnce()
      expect(fetcher.mock.calls[0][1]).toMatchObject({
        method: 'GET',
        headers: {
          Accept: 'text/event-stream',
          Authorization: 'Bearer secret',
        },
      })
      expect(fetcher.mock.calls[0][0]).not.toContain('secret')
    },
  )
  it('recovers newer snapshots using cursor without duplicating updates', async () => {
    vi.useFakeTimers()
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response(wire()))
      .mockResolvedValueOnce(
        response(wire() + wire(snapshot(3, 'waiting_input')) + end()),
      )
    const stream = setup(fetcher)
    await vi.advanceTimersByTimeAsync(1000)
    await stream.done
    expect(
      stream.onSnapshot.mock.calls.map(([value]) => value.revision),
    ).toEqual([1, 3])
    expect(fetcher.mock.calls[1][1]?.headers).toMatchObject({
      'Last-Event-ID': `${runId}:1`,
    })
    expect(stream.onEnd).toHaveBeenCalledOnce()
  })
  it('exhausts retry budget when repeated duplicate snapshots end abruptly', async () => {
    vi.useFakeTimers()
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async () => response(wire()))
    const stream = setup(fetcher)
    await vi.advanceTimersByTimeAsync(25_000)
    await stream.done
    expect(fetcher).toHaveBeenCalledTimes(6)
    expect(stream.onSnapshot).toHaveBeenCalledOnce()
    expect(stream.onEnd).not.toHaveBeenCalled()
    expect(stream.onState).toHaveBeenLastCalledWith('unavailable')
  })
  it.each([401, 403, 404, 422, 409])(
    'does not retry HTTP %s',
    async (status) => {
      const fetcher = vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response('{}', { status }))
      const stream = setup(fetcher)
      await stream.done
      expect(fetcher).toHaveBeenCalledOnce()
      expect(stream.onState).toHaveBeenLastCalledWith(
        status === 422 || status === 409 ? 'protocol_error' : 'access_lost',
      )
      expect(stream.onSnapshot).not.toHaveBeenCalled()
    },
  )
  it('retries transient failures and sanitized unavailable events', async () => {
    vi.useFakeTimers()
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('private network details'))
      .mockResolvedValueOnce(new Response('{}', { status: 503 }))
      .mockResolvedValueOnce(
        response(
          'event: stream_error\ndata: {"version":1,"reason":"unavailable"}\n\n',
        ),
      )
      .mockResolvedValueOnce(
        response(wire(snapshot(1, 'waiting_input')) + end()),
      )
    const stream = setup(fetcher)
    await vi.advanceTimersByTimeAsync(7000)
    await stream.done
    expect(fetcher).toHaveBeenCalledTimes(4)
    expect(stream.onEnd).toHaveBeenCalledOnce()
  })
  it.each([
    end(),
    wire() + end(),
    wire(snapshot(2)) + wire(),
    wire() + wire({ ...snapshot(), customer_update: 'conflict' }),
    'event: unknown\ndata: {}\n\n',
    'event: snapshot\ndata: malformed\n\n',
  ])('stops on protocol violations', async (text) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(response(text))
    const stream = setup(fetcher)
    await stream.done
    expect(fetcher).toHaveBeenCalledOnce()
    expect(stream.onState).toHaveBeenLastCalledWith('protocol_error')
    expect(stream.onEnd).not.toHaveBeenCalled()
  })
  it('stops immediately on revoked access after a valid snapshot', async () => {
    const stream = setup(
      vi
        .fn<typeof fetch>()
        .mockResolvedValueOnce(
          response(
            wire() +
              'event: stream_error\ndata: {"version":1,"reason":"access_lost"}\n\n',
          ),
        ),
    )
    await stream.done
    expect(stream.onState).toHaveBeenLastCalledWith('access_lost')
    expect(stream.onEnd).not.toHaveBeenCalled()
  })
  it('cancels a retry timer on exit', async () => {
    vi.useFakeTimers()
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response(wire()))
    const stream = setup(fetcher)
    await vi.advanceTimersByTimeAsync(0)
    const calls = stream.onState.mock.calls.length
    stream.stop()
    await vi.advanceTimersByTimeAsync(60_000)
    await stream.done
    expect(fetcher).toHaveBeenCalledOnce()
    expect(stream.onState).toHaveBeenCalledTimes(calls)
  })
  it('ignores late bytes from the old identity and cancels the reader', async () => {
    let bodyController: ReadableStreamDefaultController<Uint8Array> | undefined
    const cancel = vi.fn()
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        bodyController = controller
      },
      cancel,
    })
    const stream = setup(
      vi.fn<typeof fetch>().mockResolvedValueOnce(
        new Response(body, {
          headers: { 'Content-Type': 'text/event-stream' },
        }),
      ),
    )
    await Promise.resolve()
    stream.stop()
    bodyController?.enqueue(
      new TextEncoder().encode(wire(snapshot(1, 'waiting_input')) + end()),
    )
    await stream.done
    expect(stream.onSnapshot).not.toHaveBeenCalled()
    expect(stream.onEnd).not.toHaveBeenCalled()
    expect(cancel).toHaveBeenCalledOnce()
  })
  it('cancels stalled body reads with a bounded timeout', async () => {
    vi.useFakeTimers()
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(async (_url, init) => {
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            init?.signal?.addEventListener(
              'abort',
              () => controller.error(new Error('aborted')),
              { once: true },
            )
          },
        })
        return new Response(body, {
          headers: { 'Content-Type': 'text/event-stream' },
        })
      })
    const stream = setup(fetcher)
    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS + 1000)
    expect(fetcher).toHaveBeenCalledTimes(2)
    stream.stop()
    await stream.done
  })
  it('allows manual reopening with the last snapshot cursor', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        response(wire(snapshot(3, 'waiting_input')) + end()),
      )
    const stream = setup(fetcher, snapshot(2))
    await stream.done
    expect(fetcher.mock.calls[0][1]?.headers).toMatchObject({
      'Last-Event-ID': `${runId}:2`,
    })
  })
})

it('reads the exact SSE bytes asserted by the Python transport test', async () => {
  const stream = setup(
    vi.fn<typeof fetch>().mockResolvedValueOnce(response(fixture)),
  )
  await stream.done
  expect(stream.onSnapshot).toHaveBeenCalledWith({
    ...snapshot(7, 'waiting_input'),
    customer_update: 'café 🐈\nquestion',
  })
  expect(stream.onEnd).toHaveBeenCalledWith('waiting_input')
})

it('retries an EOF that truncates a UTF-8 character without applying its frame', async () => {
  vi.useFakeTimers()
  const bytes = new TextEncoder().encode('event: snapshot\ndata: {"text":"🐈')
  const truncated = new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, -1))
        controller.close()
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  )
  const fetcher = vi
    .fn<typeof fetch>()
    .mockResolvedValueOnce(truncated)
    .mockResolvedValueOnce(response(wire(snapshot(1, 'waiting_input')) + end()))
  const stream = setup(fetcher)
  await vi.advanceTimersByTimeAsync(1000)
  await stream.done
  expect(fetcher).toHaveBeenCalledTimes(2)
  expect(stream.onSnapshot).toHaveBeenCalledOnce()
  expect(stream.onState).not.toHaveBeenCalledWith('protocol_error')
})

it('resets the retry budget after 30 seconds of healthy streaming', async () => {
  vi.useFakeTimers()
  const times: number[] = []
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => {
    times.push(Date.now())
    if (times.length < 4) return new Response('{}', { status: 503 })
    if (times.length === 4) {
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(wire()))
          setTimeout(
            () =>
              controller.enqueue(new TextEncoder().encode(': heartbeat\n\n')),
            15_000,
          )
          setTimeout(
            () =>
              controller.enqueue(new TextEncoder().encode(': heartbeat\n\n')),
            30_000,
          )
          setTimeout(() => controller.close(), 31_000)
        },
      })
      return new Response(body, {
        headers: { 'Content-Type': 'text/event-stream' },
      })
    }
    return response(wire(snapshot(2, 'waiting_input')) + end())
  })
  const stream = setup(fetcher, snapshot())
  await vi.advanceTimersByTimeAsync(39_000)
  await stream.done
  expect(times.map((time) => time - times[0])).toEqual([
    0, 1000, 3000, 7000, 39_000,
  ])
  expect(stream.onEnd).toHaveBeenCalledOnce()
})
