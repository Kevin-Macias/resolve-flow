import type { IssueReport } from './api'

export function reportLabel(report: IssueReport) {
  return report.description.length > 90
    ? `${report.description.slice(0, 90)}…`
    : report.description
}
export function dateLabel(value: string) {
  return new Date(value).toLocaleString()
}
