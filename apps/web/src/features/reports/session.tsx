import type { ReactNode } from 'react'

import { DemoSession } from '../session/demo-session'

export { useDemoToken, useSessionIsCurrent } from '../session/demo-session'

export function CustomerSession({ children }: { children: ReactNode }) {
  return <DemoSession>{children}</DemoSession>
}
