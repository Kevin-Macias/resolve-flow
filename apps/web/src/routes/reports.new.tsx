import { createFileRoute } from '@tanstack/react-router'
import { NewReport } from '../features/reports/screens/new-report'

export const Route = createFileRoute('/reports/new')({ component: NewReport })
