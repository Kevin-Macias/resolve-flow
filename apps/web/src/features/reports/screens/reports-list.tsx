import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'

import { reportKeys, reportsApi } from '../api'
import { ErrorNotice } from '../components/error-notice'
import { ReportStatus } from '../components/report-status'
import { dateLabel, reportLabel } from '../format'
import { useDemoToken } from '../session'

export function ReportsList() {
  const token = useDemoToken()
  const query = useQuery({
    queryKey: reportKeys.all(token),
    queryFn: ({ signal }) => reportsApi(token).list(signal),
  })
  return (
    <>
      <div className="flex items-center justify-between gap-4 max-[600px]:flex-col max-[600px]:items-start [&_p]:mt-0">
        <div>
          <p className="eyebrow">Customer workspace</p>
          <h1>My reports</h1>
        </div>
        <Link className="button-primary" to="/reports/new">
          New report
        </Link>
      </div>
      <p>
        Reports visible to your customer account. Open one to review it or
        update its affected service.
      </p>
      {query.isPending ? (
        <p role="status">Loading your reports…</p>
      ) : query.isError ? (
        <>
          <ErrorNotice error={query.error} />
          <button
            className="button-secondary"
            onClick={() => void query.refetch()}
          >
            Try again
          </button>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between gap-4">
            <p>
              {query.data.length}{' '}
              {query.data.length === 1 ? 'report' : 'reports'}
            </p>
            <button
              className="button-secondary"
              disabled={query.isFetching}
              onClick={() => void query.refetch()}
            >
              {query.isFetching ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
          {query.data.length === 0 ? (
            <section className="card my-5 border-line py-12 text-center">
              <h2>No reports yet</h2>
              <p>
                Describe a problem so your support team has a record of what
                happened.
              </p>
              <Link to="/reports/new">Create your first report</Link>
            </section>
          ) : (
            <ul className="list-none p-0">
              {[...query.data]
                .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
                .map((report) => (
                  <li key={report.id} className="card my-5 border-line">
                    <div className="flex items-center justify-between gap-4 max-[600px]:flex-col max-[600px]:items-start [&_h2]:mb-0 [&_h2]:wrap-anywhere [&_a]:no-underline [&_a:hover]:underline">
                      <h2>
                        <Link
                          to="/reports/$reportId"
                          params={{ reportId: report.id }}
                        >
                          {reportLabel(report)}
                        </Link>
                      </h2>
                      <ReportStatus report={report} />
                    </div>
                    <p>
                      {report.affected_service?.label ?? 'No service specified'}
                    </p>
                    <p className="hint">
                      Updated {dateLabel(report.updated_at)}
                    </p>
                  </li>
                ))}
            </ul>
          )}
        </>
      )}
    </>
  )
}
