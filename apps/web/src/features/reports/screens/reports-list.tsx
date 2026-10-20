import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'

import { reportKeys, reportsApi } from '../api'
import { ErrorNotice } from '../components/error-notice'
import { ReportIcon } from '../components/report-icon'
import { ReportStatus } from '../components/report-status'
import { dateLabel, reportLabel } from '../format'
import { useSessionToken } from '../session'

export function ReportsList() {
  const token = useSessionToken()
  const query = useQuery({
    queryKey: reportKeys.all(token),
    queryFn: ({ signal }) => reportsApi(token).list(signal),
  })
  return (
    <>
      <div className="reports-page-heading">
        <div>
          <p className="eyebrow">Your support space</p>
          <h1>My reports</h1>
          <p className="reports-page-description">Review your account’s reports and keep track of their status.</p>
        </div>
        <Link className="button-primary gap-2" to="/reports/new">
          <svg className="size-4" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
          New report
        </Link>
      </div>
      <section className="reports-collection" aria-label="Reports in your customer account" aria-busy={query.isFetching}>
        {query.isPending ? (
          <p role="status" className="reports-loading">Loading your reports…</p>
        ) : query.isError ? (
          <div className="p-6">
            <ErrorNotice error={query.error} />
            <button
              className="button-secondary"
              onClick={() => void query.refetch()}
            >
              Try again
            </button>
          </div>
        ) : (
          <>
            <div className="reports-collection-toolbar">
              <p className="m-0 text-sm font-medium text-muted">
                {query.data.length}{' '}
                {query.data.length === 1 ? 'report' : 'reports'}
              </p>
              <button
                className="reports-refresh"
                disabled={query.isFetching}
                onClick={() => void query.refetch()}
              >
                {query.isFetching ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>
            {query.data.length === 0 ? (
              <section className="reports-empty">
                <span className="reports-empty-icon"><ReportIcon className="size-7" /></span>
                <h2>No reports yet</h2>
                <p>
                  Describe a problem so your support team has a record of what
                  happened.
                </p>
                <Link className="button-secondary" to="/reports/new">Create your first report</Link>
            </section>
          ) : (
            <ul className="reports-list">
              {[...query.data]
                .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
                .map((report) => (
                  <li key={report.id} className="report-list-item">
                    <span className="report-list-icon"><ReportIcon className="size-5" /></span>
                    <div className="min-w-0 flex-1">
                      <div className="report-list-heading">
                        <h2 className="m-0 min-w-0 text-base leading-relaxed wrap-anywhere">
                          <Link
                            className="report-list-link"
                            to="/reports/$reportId"
                            params={{ reportId: report.id }}
                          >
                            {reportLabel(report)}
                          </Link>
                        </h2>
                        <ReportStatus report={report} />
                      </div>
                      <div className="report-list-meta">
                        <span>
                          {report.affected_service?.label ?? 'No service specified'}
                        </span>
                        <span>Updated <time dateTime={report.updated_at}>{dateLabel(report.updated_at)}</time></span>
                      </div>
                    </div>
                    <svg className="report-list-arrow" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg>
                  </li>
                ))}
            </ul>
          )}
        </>
      )}
      </section>
    </>
  )
}
