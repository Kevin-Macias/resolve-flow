import { limitErrorMessage } from '../api/limit-errors'
import { createApiClient, type components } from '@resolve-flow/api-client'

import {
  parseReportResponse,
  reportListResponseSchema,
  reportResponseSchema,
  ReportResponseError,
} from './response-validation'

export type IssueReport = components['schemas']['IssueReportResponse']
export type CreateReport = components['schemas']['IssueReportCreate']
export type UpdateReport = components['schemas']['IssueReportUpdate']

export const reportErrorMessages: Readonly<Partial<Record<number, string>>> = {
  401: 'Your session was not accepted. End this session and sign in again.',
  403: 'This identity cannot access customer reports.',
  404: 'This report is unavailable to your account. It may be missing or no longer visible.',
  422: 'Check the description and service code. The supplied values were not accepted.',
}

export const defaultReportErrorMessage =
  'The request could not be completed. Refresh to check the current state before repeating a change.'

export class ReportApiError extends Error {
  constructor(public readonly status: number) {
    super(limitErrorMessage(status) ?? reportErrorMessages[status] ?? defaultReportErrorMessage)
  }
}

export function reportsApi(token: string) {
  const client = createApiClient(
    import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  )
  const headers = { Authorization: `Bearer ${token}` }
  return {
    async list(signal?: AbortSignal) {
      const { data, response } = await client.GET('/issue-reports/', {
        headers,
        signal,
      })
      if (!response.ok || !data) throw new ReportApiError(response.status)
      return parseReportResponse(reportListResponseSchema, data)
    },
    async get(id: string, signal?: AbortSignal) {
      const { data, response } = await client.GET(
        '/issue-reports/{report_id}',
        { headers, signal, params: { path: { report_id: id } } },
      )
      if (!response.ok || !data) throw new ReportApiError(response.status)
      return parseReportResponse(reportResponseSchema, data)
    },
    async create(body: CreateReport) {
      const { data, response } = await client.POST('/issue-reports/', {
        headers,
        body,
      })
      if (!response.ok || !data) throw new ReportApiError(response.status)
      return parseReportResponse(reportResponseSchema, data)
    },
    async update(id: string, body: UpdateReport) {
      const { data, response } = await client.PATCH(
        '/issue-reports/{report_id}',
        { headers, body, params: { path: { report_id: id } } },
      )
      if (!response.ok || !data) throw new ReportApiError(response.status)
      return parseReportResponse(reportResponseSchema, data)
    },
    async archive(id: string) {
      const { response } = await client.DELETE('/issue-reports/{report_id}', {
        headers,
        params: { path: { report_id: id } },
      })
      if (response.status !== 204) throw new ReportApiError(response.status)
    },
  }
}

export function errorMessage(error: unknown) {
  return error instanceof ReportApiError || error instanceof ReportResponseError
    ? error.message
    : 'Could not reach ResolveFlow. Check your connection and refresh before repeating a change.'
}

// Scope both list and detail caches to the current session. Never share a client
// across SSR requests; the session provider owns it and clears it on exit.
export const reportKeys = {
  all: (token: string) => ['reports', token] as const,
  detail: (token: string, id: string) => ['reports', token, id] as const,
}
