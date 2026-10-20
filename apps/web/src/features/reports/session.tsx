import type { ReactNode } from 'react'

import { WorkspaceSession } from '../session/workspace-session'

export { useSessionToken, useSessionIsCurrent } from '../session/workspace-session'

export function CustomerSession({ children }: { children: ReactNode }) {
  return <WorkspaceSession>{children}</WorkspaceSession>
}
