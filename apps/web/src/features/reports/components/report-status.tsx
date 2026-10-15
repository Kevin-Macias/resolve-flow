import type { IssueReport } from '../api'

export function ReportStatus({ report }: { report: IssueReport }) {
  return (
    <span className="inline-block rounded-full border border-[#d0e1d6] bg-[#e8f1eb] px-3 py-1.5 text-[0.8rem] whitespace-nowrap text-[#285a45] capitalize">
      {report.status.replaceAll('_', ' ')}
    </span>
  )
}
