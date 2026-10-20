import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useSessionToken } from '../session/workspace-session'
import {
  metricsAccessLost,
  metricsApi,
  metricsErrorMessage,
  MetricsResponseError,
} from './api'
import type { SupportMetrics } from './schemas'
import { AccountingPanel } from './accounting'

type ReadResult =
  | { kind: 'ready'; value: SupportMetrics }
  | { kind: 'unavailable'; message: string; accessLost: boolean }

export function MetricsPanel({
  reportId,
  onAccessLost,
}: {
  reportId: string
  onAccessLost: () => void
}) {
  const [showAccounting, setShowAccounting] = useState(false)
  const token = useSessionToken()
  const [online, setOnline] = useState(true)
  const [disconnectedAt, setDisconnectedAt] = useState(0)
  useEffect(() => {
    const update = () => {
      setOnline(navigator.onLine)
      if (!navigator.onLine) setDisconnectedAt(Date.now())
    }
    update()
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])
  const query = useQuery({
    queryKey: ['support-metrics', token, reportId],
    gcTime: 0,
    staleTime: 0,
    retry: false,
    queryFn: async ({ signal }): Promise<ReadResult> => {
      try {
        return {
          kind: 'ready',
          value: await metricsApi(token, reportId).read(signal),
        }
      } catch (error) {
        if (metricsAccessLost(error) || error instanceof MetricsResponseError)
          return {
            kind: 'unavailable',
            message: metricsErrorMessage(error),
            accessLost: metricsAccessLost(error),
          }
        throw error
      }
    },
  })
  const lost = query.data?.kind === 'unavailable' && query.data.accessLost
  useEffect(() => {
    if (lost) onAccessLost()
  }, [lost, onAccessLost])
  const saved = query.data?.kind === 'ready' ? query.data.value : undefined
  const record = saved?.metrics
  const error =
    query.data?.kind === 'unavailable'
      ? query.data.message
      : query.isError
        ? metricsErrorMessage(query.error)
        : undefined
  return (
    <section className="card mt-6" aria-labelledby="metrics-heading">
      <h2 id="metrics-heading" className="section-title">
        Execution metrics
      </h2>
      <p className="hint">Latest extraction only · not a run total.</p>
      {query.isPending && <p role="status">Loading saved metrics…</p>}
      {error && (
        <p role="alert" className="notice">
          {error}
        </p>
      )}
      {!online && (
        <p role="status">Connection lost. Reconnect to refresh metrics.</p>
      )}
      {saved &&
        (query.isError ||
          !online ||
          query.fetchStatus === 'paused' ||
          query.dataUpdatedAt <= disconnectedAt) && (
          <p className="notice">These saved metrics may be stale.</p>
        )}
      {saved && (
        <>
          {saved.provider_mode && (
            <p className="notice">
              {saved.provider_mode === 'offline'
                ? 'Offline simulation'
                : 'Live provider mode'}
            </p>
          )}
          {saved.operation_pending && (
            <p className="notice">
              An accepted operation is pending. Metrics describe the last saved
              extraction, not the pending operation.
            </p>
          )}
          {!record ? (
            <p>No saved extraction metrics yet.</p>
          ) : (
            <>
              <dl className="detail-list">
                <div>
                  <dt>Configured model</dt>
                  <dd className="break-all">{record.model}</dd>
                </div>
                <div>
                  <dt>Prompt</dt>
                  <dd className="break-all">
                    {record.prompt_id} · version {record.prompt_version}
                  </dd>
                </div>
                <div>
                  <dt>Attempts</dt>
                  <dd>{record.attempts}</dd>
                </div>
                <div>
                  <dt>Input tokens</dt>
                  <dd>{record.usage?.input_tokens ?? 'Not recorded'}</dd>
                </div>
                <div>
                  <dt>Output tokens</dt>
                  <dd>{record.usage?.output_tokens ?? 'Not recorded'}</dd>
                </div>
                <div>
                  <dt>Total tokens</dt>
                  <dd>{record.usage?.total_tokens ?? 'Not recorded'}</dd>
                </div>
                <div>
                  <dt>Latency</dt>
                  <dd>Not recorded</dd>
                </div>
                <div>
                  <dt>Estimated cost</dt>
                  <dd>Not recorded</dd>
                </div>
              </dl>
              <p className="hint">
                Token usage describes the final returned provider response. It
                does not account for all retry attempts. Latency and cost were
                not recorded in this snapshot. Open model attempt history for
                per-attempt measurements and estimates.
              </p>
            </>
          )}
        </>
      )}
      <button
        className="button-secondary mt-4"
        disabled={query.isFetching || lost || !online}
        onClick={() => void query.refetch()}
      >
        {query.isFetching ? 'Refreshing metrics…' : 'Refresh metrics'}
      </button>
      <button className="button-secondary mt-4 ml-3" onClick={() => setShowAccounting(!showAccounting)}>{showAccounting ? 'Hide model attempt history' : 'Show model attempt history'}</button>
      {showAccounting && <AccountingPanel key={`${token}:${reportId}`} reportId={reportId} onAccessLost={onAccessLost} />}
    </section>
  )
}
