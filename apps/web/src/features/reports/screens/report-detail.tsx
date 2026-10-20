import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useCallback, useState } from 'react'

import { IntakePanel } from '../../customer-intake/components/intake-panel'

import { reportKeys, reportsApi } from '../api'
import { ErrorNotice } from '../components/error-notice'
import { ReportContent } from '../components/report-content'
import { useSessionToken } from '../session'

export function ReportDetail({ reportId }: { reportId: string }) {
  const token = useSessionToken()
  const [lostScope, setLostScope] = useState('')
  const scope = `${token}:${reportId}`
  const accessLost = lostScope === scope
  const onAccessLost = useCallback(() => setLostScope(scope), [scope])
  const query = useQuery({
    queryKey: reportKeys.detail(token, reportId),
    queryFn: ({ signal }) => reportsApi(token).get(reportId, signal),
  })
  return (
    <>
      <Link to="/reports">← My reports</Link>
      {query.isPending ? (
        <p role="status">Loading report…</p>
      ) : query.isError || accessLost ? (
        <>
          <h1>Report unavailable</h1>
          {accessLost ? (
            <p role="alert" className="notice-error">
              Your access to this report is no longer available.
            </p>
          ) : (
            <ErrorNotice error={query.error} />
          )}
          <button
            className="button-secondary"
            onClick={() =>
              void query.refetch().then((result) => {
                if (result.isSuccess) setLostScope('')
              })
            }
          >
            Refresh report
          </button>
        </>
      ) : (
        <>
          <ReportContent
            key={query.data.id}
            report={query.data}
            refreshing={query.isFetching}
            refresh={async () => {
              const result = await query.refetch()
              return result.isSuccess
            }}
          />
          <IntakePanel
            key={scope}
            reportId={reportId}
            onAccessLost={onAccessLost}
          />
        </>
      )}
    </>
  )
}
