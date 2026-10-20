import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useCallback, useEffect, useState } from 'react'

import { uuidSchema } from '../../../lib/validation'
import { useSessionToken } from '../../session/workspace-session'
import { EvidencePanel } from '../../evidence/evidence-panel'
import { MetricsPanel } from '../../metrics/metrics-panel'
import { ActionPanel } from '../../approval/action-panel'
import {
  SupportApiError,
  TimelineResponseError,
  supportRunsApi,
  timelineErrorMessage,
} from '../api'
import { ExecutionTimeline } from '../components/execution-timeline'
import type { SupportRun } from '../schemas'

type ReadResult =
  | { kind: 'ready'; run: SupportRun }
  | { kind: 'unavailable'; message: string; accessLost: boolean }

export function SupportReport({ reportId }: { reportId: string }) {
  const token = useSessionToken()
  const scope = `${token}:${reportId}`
  const [lostScope, setLostScope] = useState('')
  const onAccessLost = useCallback(() => setLostScope(scope), [scope])
  const valid = uuidSchema.safeParse(reportId).success
  const query = useQuery({
    queryKey: ['support-run', token, reportId],
    enabled: valid,
    gcTime: 0,
    staleTime: 0,
    retry: false,
    queryFn: async ({ signal }): Promise<ReadResult> => {
      try {
        return {
          kind: 'ready',
          run: await supportRunsApi(token).get(reportId, signal),
        }
      } catch (error) {
        // Replace cached protected data on access loss or invalid responses.
        if (
          error instanceof TimelineResponseError ||
          (error instanceof SupportApiError &&
            [401, 403, 404, 422].includes(error.status))
        ) {
          return {
            kind: 'unavailable',
            message: timelineErrorMessage(error),
            accessLost:
              error instanceof SupportApiError &&
              [401, 403].includes(error.status),
          }
        }
        throw error
      }
    },
  })
  // A revoked identity invalidates every protected section.
  useEffect(() => {
    if (query.data?.kind === 'unavailable' && query.data.accessLost)
      onAccessLost()
  }, [query.data, onAccessLost])
  const accessLost = lostScope === scope
  const run =
    !accessLost && query.data?.kind === 'ready' ? query.data.run : undefined
  const unavailable = accessLost || !valid || query.data?.kind === 'unavailable'
  let message: string | undefined
  if (accessLost) message = 'Your access to this report is no longer available.'
  else if (!valid) message = 'Enter a valid report ID.'
  else if (query.data?.kind === 'unavailable') message = query.data.message
  else if (query.isError) message = timelineErrorMessage(query.error)
  return (
    <>
      <Link to="/support">← Open another report</Link>
      <p className="eyebrow">Internal support</p>
      <h1>Report execution</h1>
      <p className="hint break-all">Report ID: {reportId}</p>
      {run && (
        <div className="notice mb-6">
          <p className="my-0">
            {run.simulated ? 'Offline simulation' : 'Live provider'} · Run ID:{' '}
            <span className="break-all">{run.run_id}</span>
          </p>
          {run.operation_pending && (
            <p className="mb-0">
              An accepted operation is pending. This does not establish whether
              a worker is currently running.
            </p>
          )}
        </div>
      )}
      <button
        className="button-secondary mb-6"
        disabled={accessLost || !valid || query.isFetching}
        onClick={() => void query.refetch()}
      >
        {query.isFetching ? 'Refreshing…' : 'Refresh timeline'}
      </button>
      <ExecutionTimeline
        events={run?.timeline ?? []}
        loading={valid && query.isPending}
        unavailable={unavailable}
        error={message}
        stale={Boolean(run && query.isError)}
      />
      {valid && !accessLost && (
        <EvidencePanel
          key={scope}
          reportId={reportId}
          onAccessLost={onAccessLost}
        />
      )}
      {valid && !accessLost && (
        <ActionPanel
          key={`action:${scope}`}
          reportId={reportId}
          onAccessLost={onAccessLost}
        />
      )}
      {valid && !accessLost && (
        <MetricsPanel
          key={`metrics:${scope}`}
          reportId={reportId}
          onAccessLost={onAccessLost}
        />
      )}
    </>
  )
}
