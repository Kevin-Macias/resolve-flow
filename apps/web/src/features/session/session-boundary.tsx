import { useRouterState } from '@tanstack/react-router'
import type { ReactNode } from 'react'

import { WorkspaceSession } from './workspace-session'

export function SessionBoundary({ children, authMode }: { children: ReactNode; authMode?: 'demo' | 'password' }) {
  const support = useRouterState({
    select: (state) => {
      // Match the displayed outlet, rather than a navigation still in progress.
      const pathname = state.matches.at(-1)?.pathname ?? state.location.pathname
      return pathname === '/support' || pathname.startsWith('/support/')
    },
  })
  const experience = support ? 'support' : 'customer'
  const mode = authMode ?? (import.meta.env.VITE_AUTH_MODE === 'demo' ? 'demo' : 'password')
  return (
    <WorkspaceSession key={mode === 'demo' ? `demo-${experience}` : 'password'} experience={experience} authMode={mode}>
      {children}
    </WorkspaceSession>
  )
}
