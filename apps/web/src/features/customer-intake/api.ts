import { limitErrorMessage } from '../api/limit-errors'
import { apiBaseUrl, browserApiClient, sessionHeaders } from '../api/browser-client'

import { customerRunSchema, type ClarificationRequest } from './schemas'

export const intakeErrorMessages: Readonly<Partial<Record<number, string>>> = {
  401: 'Your session was not accepted. End this session and sign in again.',
  403: 'This identity cannot access customer intake.',
  404: 'This report or its intake is unavailable to your account.',
  409: 'Intake changed or another operation is running. Refresh saved intake before taking another action.',
  422: 'The supplied reply was not accepted. Refresh saved intake and check the current questions.',
}
export class IntakeApiError extends Error {
  constructor(public readonly status: number) {
    super(
      limitErrorMessage(status) ?? intakeErrorMessages[status] ??
        'Intake could not be completed. Refresh saved intake to check whether the operation was accepted.',
    )
  }
}
export class IntakeResponseError extends Error {
  constructor() {
    super(
      'ResolveFlow returned an invalid intake response. Refresh saved intake to check its state.',
    )
  }
}
export function intakeErrorMessage(error: unknown) {
  return error instanceof IntakeApiError || error instanceof IntakeResponseError
    ? error.message
    : 'Could not reach ResolveFlow. Refresh saved intake before repeating an action; it may already have been accepted.'
}
export function isAccessLost(error: unknown) {
  return (
    error instanceof IntakeApiError && [401, 403, 404].includes(error.status)
  )
}
export const intakeKeys = {
  report: (token: string, reportId: string) =>
    ['customer-intake', token, reportId] as const,
}
export function intakeApi(token: string, reportId: string) {
  const client = browserApiClient(token)
  const headers = sessionHeaders(token)
  function parse(data: unknown, response: Response, runId?: string) {
    if (!response.ok) throw new IntakeApiError(response.status)
    const result = customerRunSchema.safeParse(data)
    if (
      !result.success ||
      result.data.report_id !== reportId ||
      (runId && result.data.run_id !== runId)
    )
      throw new IntakeResponseError()
    return result.data
  }
  return {
    async read(signal?: AbortSignal) {
      const { data, response } = await client.GET(
        '/issue-reports/{report_id}/intake-run',
        { headers, signal, params: { path: { report_id: reportId } } },
      )
      return parse(data, response)
    },
    async start() {
      const { data, response } = await client.POST(
        '/issue-reports/{report_id}/intake-run',
        { headers, body: {}, params: { path: { report_id: reportId } } },
      )
      return parse(data, response)
    },
    async clarify(runId: string, body: ClarificationRequest) {
      const { data, response } = await client.POST(
        '/intake-runs/{run_id}/clarification',
        { headers, body, params: { path: { run_id: runId } } },
      )
      return parse(data, response, runId)
    },
    async recover(runId: string, expected_revision: number) {
      const { data, response } = await client.POST(
        '/intake-runs/{run_id}/recover',
        {
          headers,
          body: { expected_revision },
          params: { path: { run_id: runId } },
        },
      )
      return parse(data, response, runId)
    },
    streamUrl(runId: string) {
      return `${apiBaseUrl(token)}/intake-runs/${runId}/events`
    },
  }
}
