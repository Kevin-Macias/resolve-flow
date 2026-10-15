import { createFileRoute } from '@tanstack/react-router'
import { ReportDetail } from '../features/reports/screens/report-detail'

export const Route = createFileRoute('/reports/$reportId')({
  component: ReportPage,
})
function ReportPage() {
  const { reportId } = Route.useParams()
  return <ReportDetail reportId={reportId} />
}
