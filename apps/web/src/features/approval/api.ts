import { limitErrorMessage } from '../api/limit-errors'
import { browserApiClient, sessionHeaders } from '../api/browser-client'

import {
  supportActionSchema,
  type ProposalRequest,
  type DecisionRequest,
} from './schemas'

export class ActionApiError extends Error {
  constructor(public readonly status: number) {
    super(
      limitErrorMessage(status) ?? (status === 409
        ? 'The action or its observations changed. Refresh and review the current saved proposal.'
        : [401, 403, 404].includes(status)
          ? 'This action is unavailable to your support identity.'
          : 'The action could not be loaded. Refresh saved action before deciding again.'
      )
    )
  }
}
export class ActionResponseError extends Error {
  constructor() {
    super(
      'ResolveFlow returned an invalid action response. Refresh to try again.',
    )
  }
}
export const actionAccessLost = (error: unknown) =>
  error instanceof ActionApiError && [401, 403, 404].includes(error.status)
export const actionErrorMessage = (error: unknown) =>
  error instanceof ActionApiError || error instanceof ActionResponseError
    ? error.message
    : 'Could not reach ResolveFlow. Your decision may have been saved. Refresh before deciding again.'

export function actionsApi(token: string, reportId: string) {
  const client = browserApiClient(token)
  const headers = sessionHeaders(token)
  const params = { path: { report_id: reportId } }
  function parse(data: unknown, response: Response) {
    if (!response.ok) throw new ActionApiError(response.status)
    const result = supportActionSchema.safeParse(data)
    if (!result.success || result.data.report_id !== reportId)
      throw new ActionResponseError()
    return result.data
  }
  return {
    async read(signal?: AbortSignal) {
      const { data, response } = await client.GET(
        '/support/issue-reports/{report_id}/action',
        { headers, params, signal },
      )
      return parse(data, response)
    },
    async prepare(body: ProposalRequest) {
      const { data, response } = await client.POST(
        '/support/issue-reports/{report_id}/proposal',
        { headers, params, body },
      )
      return parse(data, response)
    },
    async decide(runId: string, body: DecisionRequest) {
      const { data, response } = await client.POST(
        '/support/issue-reports/{report_id}/runs/{run_id}/decision',
        {
          headers,
          params: { path: { report_id: reportId, run_id: runId } },
          body,
        },
      )
      const value = parse(data, response)
      if (
        value.run_id !== runId ||
        value.proposal?.action_id !== body.action_id ||
        value.proposal.version !== body.version ||
        value.fingerprint !== body.fingerprint
      )
        throw new ActionResponseError()
      return value
    },
  }
}
