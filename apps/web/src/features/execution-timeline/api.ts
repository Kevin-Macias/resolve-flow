import { limitErrorMessage } from '../api/limit-errors'
import { createApiClient } from '@resolve-flow/api-client'

import { supportRunSchema } from './schemas'

export const supportErrorMessages: Readonly<Partial<Record<number, string>>> = {
  401: 'Your demo identity was not accepted. End this session and enter a valid support token.',
  403: 'This identity cannot access support timelines.',
  404: 'This report or its saved run is unavailable to your support identity.',
  422: 'Enter a valid report ID.',
}

export class SupportApiError extends Error {
  constructor(public readonly status: number) {
    super(
      limitErrorMessage(status) ?? supportErrorMessages[status] ??
        'The saved timeline could not be loaded. Refresh to try again.',
    )
  }
}

export class TimelineResponseError extends Error {
  constructor() {
    super(
      'ResolveFlow returned an invalid timeline response. Refresh to try again.',
    )
  }
}

export function timelineErrorMessage(error: unknown) {
  return error instanceof SupportApiError ||
    error instanceof TimelineResponseError
    ? error.message
    : 'Could not reach ResolveFlow. Check your connection and refresh.'
}

export function supportRunsApi(token: string) {
  const client = createApiClient(
    import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  )
  return {
    async get(reportId: string, signal?: AbortSignal) {
      const { data, response } = await client.GET(
        '/support/issue-reports/{report_id}/intake-run',
        {
          headers: { Authorization: `Bearer ${token}` },
          params: { path: { report_id: reportId } },
          signal,
        },
      )
      if (!response.ok) throw new SupportApiError(response.status)
      const result = supportRunSchema.safeParse(data)
      if (!result.success || result.data.report_id !== reportId)
        throw new TimelineResponseError()
      return result.data
    },
  }
}
