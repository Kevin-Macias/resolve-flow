import { createFileRoute } from '@tanstack/react-router'
import { SupportHome } from '../features/execution-timeline/screens/support-home'

export const Route = createFileRoute('/support/')({ component: SupportHome })
