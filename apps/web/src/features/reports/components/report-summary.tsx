import type { IssueReport } from '../api'
import { dateLabel } from '../format'

export function ReportSummary({ report }: { report: IssueReport }) {
  return (
    <section className="card my-5 border-line">
      <h2>What you reported</h2>
      <p className="whitespace-pre-wrap wrap-anywhere">
        {report.description}
      </p>
      <dl className="mb-0 grid grid-cols-3 gap-6 border-t border-[#e4e8e1] pt-5 max-[600px]:grid-cols-1">
        <div>
          <dt>Affected service</dt>
          <dd>
            {report.affected_service
              ? `${report.affected_service.label} (${report.affected_service.code})`
              : 'No service specified'}
          </dd>
        </div>
        <div>
          <dt>Submitted</dt>
          <dd>{dateLabel(report.created_at)}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{dateLabel(report.updated_at)}</dd>
        </div>
      </dl>
    </section>
  )
}
