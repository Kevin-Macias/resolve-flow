import { limitErrorMessage } from '../api/limit-errors'
import { browserApiClient, sessionHeaders } from '../api/browser-client'

import { supportEvidenceSchema } from './schemas'

export class EvidenceApiError extends Error {
  constructor(public readonly status: number) {
    super(
      limitErrorMessage(status) ?? (status === 409
        ? 'An operation is running or needs review. Refresh saved evidence before continuing.'
        : [401, 403, 404].includes(status)
          ? 'Evidence is unavailable to your support identity.'
          : 'Evidence could not be loaded. Refresh saved evidence before repeating an analysis.'
      )
    )
  }
}
export class EvidenceResponseError extends Error {
  constructor() {
    super('ResolveFlow returned invalid evidence. Refresh to try again.')
  }
}
export const evidenceErrorMessage = (error: unknown) =>
  error instanceof EvidenceApiError || error instanceof EvidenceResponseError
    ? error.message
    : 'Could not reach ResolveFlow. Refresh saved evidence; the analysis may have been accepted.'
export const evidenceAccessLost = (error: unknown) =>
  error instanceof EvidenceApiError && [401, 403, 404].includes(error.status)

export function evidenceApi(token: string, reportId: string) {
  const client = browserApiClient(token)
  const headers = sessionHeaders(token)
  const params = { path: { report_id: reportId } }
  function parse(data: unknown, response: Response) {
    if (!response.ok) throw new EvidenceApiError(response.status)
    const result = supportEvidenceSchema.safeParse(data)
    if (!result.success || result.data.report_id !== reportId)
      throw new EvidenceResponseError()
    return result.data
  }
  return {
    async read(signal?: AbortSignal) {
      const { data, response } = await client.GET(
        '/support/issue-reports/{report_id}/evidence-analysis',
        { headers, params, signal },
      )
      return parse(data, response)
    },
    async create(operationId: string) {
      const { data, response } = await client.POST(
        '/support/issue-reports/{report_id}/evidence-analyses',
        { headers, params, body: { operation_id: operationId } },
      )
      const saved = parse(data, response)
      if (saved.operation_id !== operationId) throw new EvidenceResponseError()
      return saved
    },
  }
}
