import { useRouterState } from '@tanstack/react-router'
import type { ReactNode } from 'react'

import { DemoSession } from './demo-session'

export function SessionBoundary({ children }: { children: ReactNode }) {
  const support = useRouterState({
    select: (state) =>
      state.location.pathname === '/support' ||
      state.location.pathname.startsWith('/support/'),
  })
  const experience = support ? 'support' : 'customer'
  return (
    <DemoSession key={experience} experience={experience}>
      {children}
    </DemoSession>
  )
}
