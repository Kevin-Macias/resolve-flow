import { createFileRoute } from '@tanstack/react-router'
import { ReportsList } from '../features/reports/screens/reports-list'

export const Route = createFileRoute('/reports/')({ component: ReportsList })
