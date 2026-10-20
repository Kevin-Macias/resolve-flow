import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navigate } from '@tanstack/react-router'
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { CustomerSignIn, SupportSignIn } from './sign-in-page'
import { WorkspaceHeader } from './workspace-header'
import { accountApi } from './account-api'

const SessionContext = createContext<{
  token: string
  isCurrent: () => boolean
}>({
  token: '',
  isCurrent: () => false,
})
export function useSessionToken() {
  return useContext(SessionContext).token
}
export function useSessionIsCurrent() {
  return useContext(SessionContext).isCurrent
}

export function WorkspaceSession({
  children,
  experience = 'customer',
  authMode = 'demo',
}: {
  children: ReactNode
  experience?: 'customer' | 'support'
  authMode?: 'demo' | 'password'
}) {
  const SignIn = experience === 'support' ? SupportSignIn : CustomerSignIn
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, staleTime: 30_000 },
          mutations: { retry: false },
        },
      }),
  )
  const [session, setSession] = useState<{ token: string; role: 'customer' | 'support' } | null>(null)
  const token = session?.token ?? ''
  const generation = useRef(0)
  const sessionGeneration = generation.current
  const [signOutNotice, setSignOutNotice] = useState('')
  useEffect(
    () => () => {
      generation.current += 1
      void client.cancelQueries()
      client.clear()
    },
    [client],
  )
  function connect(value: string, role: 'customer' | 'support' = experience) {
    generation.current += 1
    setSession({ token: value, role })
    setSignOutNotice('')
  }
  async function disconnect() {
    const previousToken = token
    generation.current += 1
    const endedAt = generation.current
    void client.cancelQueries()
    client.clear()
    setSession(null)
    setSignOutNotice('')
    if (authMode === 'password') {
      try { await accountApi.logout(previousToken) }
      catch { if (generation.current === endedAt) setSignOutNotice('Signed out on this browser. Server sign-out could not be confirmed; that session remains valid until revoked or expired.') }
    }
  }
  return (
    <QueryClientProvider client={client}>
      {!token ? (
        <SignIn authMode={authMode} onConnect={connect} notice={signOutNotice} />
      ) : session?.role !== experience ? (
        <Navigate to={session?.role === 'support' ? '/support' : '/reports'} replace />
      ) : (
        <>
          <WorkspaceHeader experience={experience} allowWorkspaceSwitch={authMode === 'demo'} onSignOut={() => void disconnect()} />
          <main className="workspace-content">
            <SessionContext.Provider
              value={{
                token,
                isCurrent: () => generation.current === sessionGeneration,
              }}
            >
              <div key={token}>{children}</div>
            </SessionContext.Provider>
          </main>
        </>
      )}
    </QueryClientProvider>
  )
}
