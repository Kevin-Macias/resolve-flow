import { createApiClient } from '@resolve-flow/api-client'
import type { components } from '@resolve-flow/api-client'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { z } from 'zod'
import { useDemoToken } from '../session/demo-session'
import { MetricsApiError, MetricsResponseError, metricsAccessLost, metricsErrorMessage } from './api'

const count = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER)
const decimal = z.string().regex(/^(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/).refine((value) => Number.isFinite(Number(value)))
const usage = z.strictObject({ input_tokens: count, output_tokens: count, total_tokens: count, cached_input_tokens: count.nullable() })
const rate = z.strictObject({ provider: z.literal('openai'), model: z.string().min(1), input_per_million: decimal, output_per_million: decimal, cached_input_per_million: decimal.nullable() })
const cost = z.strictObject({ usd: decimal, pricing_version: z.string().min(1), model: z.string().min(1), rate })
const attempt = z.strictObject({
  id: z.uuid(), call_id: z.uuid(), parent_call_id: z.uuid().nullable(), request_id: z.uuid().nullable(),
  scope_type: z.enum(['intake', 'evidence']), scope_id: z.uuid(), operation_id: z.uuid(),
  component: z.enum(['extraction', 'analysis', 'embedding']), provider_mode: z.enum(['offline', 'live']),
  configured_model: z.string().min(1), resolved_model: z.string().min(1).nullable(),
  prompt_id: z.string().min(1).nullable(), prompt_version: z.string().min(1).nullable(), attempt: count.min(1),
  outcome: z.enum(['started', 'response_received', 'refused', 'provider_error', 'timeout', 'cancelled']),
  started_at: z.iso.datetime({ offset: true }), finished_at: z.iso.datetime({ offset: true }).nullable(),
  latency_ms: z.number().finite().nonnegative().nullable(), usage: usage.nullable(), cost: cost.nullable(),
  cost_status: z.enum(['pending', 'offline', 'usage_unavailable', 'pricing_unavailable', 'rate_unavailable', 'cached_usage_unavailable', 'cached_rate_unavailable', 'invalid_usage', 'available']),
}).superRefine((row, ctx) => {
  if ((row.outcome === 'started') !== (row.finished_at === null) || (row.cost !== null) !== (row.cost_status === 'available') || (row.cost !== null && row.provider_mode !== 'live') || (row.finished_at !== null && (row.latency_ms === null || Date.parse(row.finished_at) < Date.parse(row.started_at))) || (row.usage && (row.usage.input_tokens + row.usage.output_tokens !== row.usage.total_tokens || (row.usage.cached_input_tokens ?? 0) > row.usage.input_tokens)))
    ctx.addIssue({ code: 'custom', message: 'Inconsistent model attempt.' })
})
const totalsSchema = z.strictObject({
  attempts: count, retries: count, live_attempts: count, offline_attempts: count,
  unfinished_attempts: count, missing_live_usage: count, missing_live_cost: count,
  known_live_input_tokens: count, known_live_output_tokens: count, known_live_total_tokens: count,
  known_live_cost_usd: decimal, known_live_provider_ms: z.number().finite().nonnegative(),
  missing_live_latency: count, coverage_complete: z.boolean(), cost_complete: z.boolean(),
})
export const accountingSchema = z.strictObject({
  version: z.literal(1), report_id: z.uuid(), offset: count, next_offset: count.nullable(), attempts: z.array(attempt).max(50),
  totals: totalsSchema,
  scopes: z.array(z.strictObject({ scope_type: z.enum(['intake', 'evidence']), scope_id: z.uuid(), totals: totalsSchema })),
}).superRefine((value, ctx) => {
  const t = value.totals
  if (t.live_attempts + t.offline_attempts !== t.attempts || t.unfinished_attempts > t.attempts || t.missing_live_cost > t.live_attempts || t.missing_live_usage > t.live_attempts || t.missing_live_latency > t.live_attempts || t.known_live_input_tokens + t.known_live_output_tokens !== t.known_live_total_tokens || (t.cost_complete && (!t.coverage_complete || t.missing_live_cost !== 0 || t.live_attempts === 0)) || (value.next_offset !== null && (value.next_offset !== value.offset + 50 || value.next_offset >= t.attempts)))
    ctx.addIssue({ code: 'custom', message: 'Inconsistent accounting totals.' })
})

export async function readAccounting(token: string, reportId: string, offset: number, signal?: AbortSignal) {
  const client = createApiClient(import.meta.env.VITE_API_URL ?? 'http://localhost:8000')
  const { data, response } = await client.GET('/support/issue-reports/{report_id}/model-accounting', {
    params: { path: { report_id: reportId }, query: { offset } }, headers: { Authorization: `Bearer ${token}` }, signal,
  })
  if (!response.ok) throw new MetricsApiError(response.status)
  const parsed = accountingSchema.safeParse(data)
  if (!parsed.success || parsed.data.report_id !== reportId || parsed.data.offset !== offset) throw new MetricsResponseError()
  return parsed.data satisfies components['schemas']['History']
}

export function AccountingPanel({ reportId, onAccessLost }: { reportId: string; onAccessLost: () => void }) {
  const token = useDemoToken()
  const [offset, setOffset] = useState(0)
  const query = useQuery({    
queryKey: ['model-accounting', token, reportId, offset], gcTime: 0, staleTime: 0, retry: false,
    queryFn: ({ signal }) => readAccounting(token, reportId, offset, signal),
  })
  const lost = metricsAccessLost(query.error)
  useEffect(() => { if (lost) onAccessLost() }, [lost, onAccessLost])
  // Invalid/denied reads hide saved values; temporary read failures retain a stale view.
  const value = lost || query.error instanceof MetricsResponseError ? undefined : query.data
  const t = value?.totals
  return <div className="mt-6 border-t border-line pt-4">
    <h3 className="section-title">Model attempt history</h3>
    <p className="hint">Saved attempts across intake and evidence operations. Provider time excludes backoff, database work, and human waits.</p>
    {query.isPending && <p role="status">Loading model attempts…</p>}
    {query.isError && <p role="alert" className="notice">{metricsErrorMessage(query.error)}</p>}
    {value && (query.isError || query.fetchStatus === 'paused') && <p className="notice">These saved accounting records may be stale.</p>}
    {t && <>
      {!t.coverage_complete && <p className="notice">Earlier work has no complete attempt history. Subtotals cover recorded attempts only.</p>}
      <p>{t.attempts} saved attempts · {t.retries} retries · {t.offline_attempts} offline attempts</p>
      {t.unfinished_attempts > 0 && <p className="notice">{t.unfinished_attempts} starts have no recorded completion. Provider usage and cost may be unknown.</p>}
      {t.live_attempts === 0 ? <p>No live attempts recorded. Offline simulation is not a measured provider bill.</p> : <dl className="detail-list">
        <div><dt>Known live token subtotal</dt><dd>{t.known_live_total_tokens} ({t.missing_live_usage} attempts missing usage)</dd></div>
        <div><dt>{t.cost_complete ? 'Estimated live cost' : 'Known live cost subtotal (partial)'}</dt><dd>USD {t.known_live_cost_usd} · {t.missing_live_cost} attempts without estimates</dd></div>
        <div><dt>Measured live provider time</dt><dd>{t.known_live_provider_ms.toFixed(1)} ms · {t.missing_live_latency} attempts unmeasured</dd></div>
      </dl>}
      <details className="mt-3"><summary>Totals by intake run and evidence operation</summary>
        {value?.scopes.map(scope => <p key={`${scope.scope_type}:${scope.scope_id}`} className="mt-2 break-all">
          {scope.scope_type === 'intake' ? 'Intake run' : 'Evidence operation'} {scope.scope_id}: {scope.totals.attempts} attempts · {scope.totals.retries} retries · {scope.totals.live_attempts === 0 ? 'no live attempts' : `USD ${scope.totals.known_live_cost_usd}${scope.totals.cost_complete ? ' estimated' : ' known subtotal (partial)'}`}.
        </p>)}
      </details>
      {value?.attempts.map(row => <details key={row.id} className="mt-3 border-t border-line pt-3">
        <summary>{row.scope_type} · {row.component} · {row.configured_model} · attempt {row.attempt} · {row.outcome.replaceAll('_', ' ')}</summary>
        <dl className="detail-list mt-2">
          <div><dt>Mode</dt><dd>{row.provider_mode === 'offline' ? 'Offline simulation' : 'Live provider mode'}</dd></div>
          <div><dt>Resolved model</dt><dd>{row.resolved_model ?? 'Not reported'}</dd></div>
          <div><dt>Prompt</dt><dd>{row.prompt_id ? `${row.prompt_id} · ${row.prompt_version}` : 'Not applicable'}</dd></div>
          <div><dt>Provider time</dt><dd>{row.latency_ms === null ? 'Not recorded' : `${row.latency_ms.toFixed(1)} ms`}</dd></div>
          <div><dt>Reported tokens</dt><dd>{row.usage?.total_tokens ?? 'Not reported'}</dd></div>
          <div><dt>Cost estimate</dt><dd>{row.cost ? `USD ${row.cost.usd} · pricing ${row.cost.pricing_version}` : row.cost_status.replaceAll('_', ' ')}</dd></div>
          <div><dt>Call ID</dt><dd className="break-all">{row.call_id}</dd></div>
          <div><dt>Operation ID</dt><dd className="break-all">{row.operation_id}</dd></div>
        </dl>
      </details>)}
      {t.attempts === 0 && <p>No saved model attempts yet.</p>}
      <div className="mt-3 flex gap-3">
        <button className="button-secondary" disabled={offset === 0 || query.isFetching || lost} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous attempts</button>
        <button className="button-secondary" disabled={value?.next_offset == null || query.isFetching || lost} onClick={() => { if (value?.next_offset != null) setOffset(value.next_offset) }}>Next attempts</button>
      </div>
    </>}
    <button className="button-secondary mt-3" disabled={query.isFetching || lost} onClick={() => void query.refetch()}>Refresh attempt history</button>
  </div>
}
