import { createFileRoute } from '@tanstack/react-router'
import { SupportReport } from '../features/execution-timeline/screens/support-report'

export const Route = createFileRoute('/support/reports/$reportId')({
  component: SupportReportPage,
})

function SupportReportPage() {
  const { reportId } = Route.useParams()
  return <SupportReport reportId={reportId} />
}
