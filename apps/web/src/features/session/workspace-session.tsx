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
import { COOKIE_SESSION_PREFIX, SESSION_ENDED_EVENT } from '../api/browser-client'

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
  const [restoring, setRestoring] = useState(authMode === 'password')
  const [restoreError, setRestoreError] = useState(false)
  const [restoreAttempt, setRestoreAttempt] = useState(0)
  const [signingOut, setSigningOut] = useState(false)
  useEffect(() => {
    if (authMode !== 'password') return
    const controller = new AbortController()
    setRestoring(true)
    setRestoreError(false)
    void accountApi.restore(AbortSignal.any([controller.signal, AbortSignal.timeout(10_000)])).then((saved) => {
      if (controller.signal.aborted) return
      if (saved) connect(`${COOKIE_SESSION_PREFIX}${saved.session_id}:${crypto.randomUUID()}`, saved.user.user_type)
      setRestoring(false)
    }).catch(() => {
      if (!controller.signal.aborted) { setRestoreError(true); setRestoring(false) }
    })
    return () => controller.abort()
  }, [authMode, restoreAttempt])
  useEffect(() => {
    function expired(event: Event) {
      if ((event as CustomEvent<string>).detail !== token) return
      generation.current += 1
      void client.cancelQueries()
      client.clear()
      setSession(null)
      setSignOutNotice('Your session ended. Sign in again.')
    }
    window.addEventListener(SESSION_ENDED_EVENT, expired)
    return () => window.removeEventListener(SESSION_ENDED_EVENT, expired)
  }, [token, client])
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
    setSigningOut(true)
    const previousToken = token
    generation.current += 1
    const endedAt = generation.current
    void client.cancelQueries()
    client.clear()
    setSession(null)
    setSignOutNotice('')
    if (authMode === 'password') {
      try { await accountApi.logout(previousToken) }
      catch { if (generation.current === endedAt) setSignOutNotice('Server sign-out could not be confirmed. Reload may restore this session. Reconnect and sign out again.') }
    }
    setSigningOut(false)
  }
  return (
    <QueryClientProvider client={client}>
      {signingOut ? <main className="workspace-content"><p role="status">Signing out…</p></main> : restoring ? <main className="workspace-content"><p role="status">Checking your session…</p></main> : restoreError ? (
        <main className="workspace-content"><p role="alert">Could not check your session. Reconnect and try again.</p><button className="button-primary" onClick={() => setRestoreAttempt((value) => value + 1)}>Try again</button></main>
      ) : !token ? (
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
