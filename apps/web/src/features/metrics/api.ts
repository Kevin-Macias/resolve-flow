import { limitErrorMessage } from '../api/limit-errors'
import { createApiClient } from '@resolve-flow/api-client'
import { supportMetricsSchema, type GeneratedMetrics } from './schemas'

export class MetricsApiError extends Error {
  constructor(public readonly status: number) {
    super(
      limitErrorMessage(status) ?? ([401, 403, 404].includes(status)
        ? 'Metrics are unavailable to your support identity.'
        : 'Saved metrics could not be loaded. Refresh to try again.'
      )
    )
  }
}
export class MetricsResponseError extends Error {
  constructor() {
    super('ResolveFlow returned invalid metrics. Refresh to try again.')
  }
}
export function metricsErrorMessage(error: unknown) {
  return error instanceof MetricsApiError ||
    error instanceof MetricsResponseError
    ? error.message
    : 'Could not reach ResolveFlow. Check your connection and refresh.'
}
export function metricsAccessLost(error: unknown) {
  return (
    error instanceof MetricsApiError && [401, 403, 404].includes(error.status)
  )
}
export function metricsApi(token: string, reportId: string) {
  const client = createApiClient(
    import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  )
  return {
    async read(signal?: AbortSignal) {
      const { data, response } = await client.GET(
        '/support/issue-reports/{report_id}/execution-metrics',
        {
          headers: { Authorization: `Bearer ${token}` },
          params: { path: { report_id: reportId } },
          signal,
        },
      )
      if (!response.ok) throw new MetricsApiError(response.status)
      const parsed = supportMetricsSchema.safeParse(data)
      if (!parsed.success || parsed.data.report_id !== reportId)
        throw new MetricsResponseError()
      return parsed.data satisfies GeneratedMetrics
    },
  }
}
