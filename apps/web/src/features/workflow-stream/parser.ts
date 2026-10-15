import { eventIdSchema } from './schemas'

/** Incremental SSE framing. Incomplete frames at EOF are deliberately discarded. */
export type StreamFrame = { event: string; data: string; id?: string }
export class ProtocolError extends Error {}
export const MAX_FRAME_CHARS = 32_768

export class SseParser {
  private line = ''
  private skipLf = false
  private size = 0
  private event = ''
  private data: string[] = []
  private id: string | undefined

  push(chunk: string): StreamFrame[] {
    const frames: StreamFrame[] = []
    for (const char of chunk) {
      if (this.skipLf) {
        this.skipLf = false
        if (char === '\n') continue
      }
      if (++this.size > MAX_FRAME_CHARS)
        throw new ProtocolError('Frame too large')
      if (char === '\r' || char === '\n') {
        this.consumeLine(frames)
        this.skipLf = char === '\r'
      } else {
        this.line += char
      }
    }
    return frames
  }

  private consumeLine(frames: StreamFrame[]) {
    const line = this.line
    this.line = ''
    if (line === '') {
      if (this.data.length) {
        frames.push({
          event: this.event || 'message',
          data: this.data.join('\n'),
          id: this.id,
        })
      }
      this.size = 0
      this.event = ''
      this.data = []
      this.id = undefined
      return
    }
    if (line.startsWith(':')) return
    const colon = line.indexOf(':')
    const field = colon < 0 ? line : line.slice(0, colon)
    let value = colon < 0 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') this.event = value
    if (field === 'data') this.data.push(value)
    if (field === 'id') {
      if (!eventIdSchema.safeParse(value).success)
        throw new ProtocolError('Invalid event ID')
      this.id = value
    }
  }
}
