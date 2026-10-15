import type { components } from '@resolve-flow/api-client'

import { uuidSchema } from '../../lib/validation'
import { ProtocolError, type StreamFrame } from './parser'
import {
  customerSnapshotSchema,
  streamEndSchema,
  streamErrorSchema,
} from './schemas'

export { progressStates } from './schemas'
export type CustomerSnapshot = components['schemas']['CustomerSnapshot']
export type Progress = CustomerSnapshot['progress']

export function validateRunId(runId: string) {
  if (!uuidSchema.safeParse(runId).success) throw new ProtocolError('Invalid run ID')
}

export type StreamEvent =
  | { kind: 'snapshot'; snapshot: CustomerSnapshot; id: string }
  | { kind: 'stream_end'; reason: Exclude<Progress, 'processing'> }
  | { kind: 'stream_error'; reason: 'unavailable' | 'access_lost' }

export function decodeEvent(frame: StreamFrame, runId: string): StreamEvent {
  let parsed: unknown
  try {
    parsed = JSON.parse(frame.data)
  } catch {
    throw new ProtocolError('Invalid JSON')
  }
  if (frame.event === 'snapshot') {
    const result = customerSnapshotSchema.safeParse(parsed)
    if (!result.success) throw new ProtocolError('Invalid snapshot')
    const snapshot = result.data
    if (
      snapshot.run_id !== runId ||
      frame.id !== `${runId}:${snapshot.revision}`
    ) {
      throw new ProtocolError('Invalid snapshot')
    }
    return { kind: 'snapshot', snapshot, id: frame.id }
  }
  if (frame.id !== undefined)
    throw new ProtocolError('Control event cannot set a cursor')
  if (frame.event === 'stream_end') {
    const result = streamEndSchema.safeParse(parsed)
    if (!result.success) throw new ProtocolError('Invalid stream end')
    return { kind: 'stream_end', reason: result.data.reason }
  }
  if (frame.event === 'stream_error') {
    const result = streamErrorSchema.safeParse(parsed)
    if (!result.success) throw new ProtocolError('Invalid stream error')
    return { kind: 'stream_error', reason: result.data.reason }
  }
  throw new ProtocolError('Unknown event')
}

export function acceptSnapshot(
  previous: CustomerSnapshot | undefined,
  next: CustomerSnapshot,
): boolean {
  if (!previous) return true
  if (next.revision < previous.revision)
    throw new ProtocolError('Decreasing revision')
  if (next.revision > previous.revision) return true
  if (
    next.run_id !== previous.run_id ||
    next.progress !== previous.progress ||
    next.customer_update !== previous.customer_update
  ) {
    throw new ProtocolError('Conflicting duplicate')
  }
  return false
}
