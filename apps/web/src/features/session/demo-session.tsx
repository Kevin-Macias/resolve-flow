import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'

import { demoTokenSchema } from '../reports/validation'
import { AccountForm } from './account-form'
import { accountApi } from './account-api'

const SessionContext = createContext<{
  token: string
  isCurrent: () => boolean
}>({
  token: '',
  isCurrent: () => false,
})
export function useDemoToken() {
  return useContext(SessionContext).token
}
export function useSessionIsCurrent() {
  return useContext(SessionContext).isCurrent
}

export function DemoSession({
  children,
  experience = 'customer',
  authMode = 'demo',
}: {
  children: ReactNode
  experience?: 'customer' | 'support'
  authMode?: 'demo' | 'password'
}) {
  const support = experience === 'support'
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, staleTime: 30_000 },
          mutations: { retry: false },
        },
      }),
  )
  const [token, setToken] = useState('')
  const generation = useRef(0)
  const sessionGeneration = generation.current
  const [enteredToken, setEnteredToken] = useState('')
  const [signOutNotice, setSignOutNotice] = useState('')
  useEffect(
    () => () => {
      generation.current += 1
      void client.cancelQueries()
      client.clear()
    },
    [client],
  )
  function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const result = demoTokenSchema.safeParse(enteredToken)
    if (!result.success) return
    generation.current += 1
    setToken(result.data)
    setEnteredToken('')
  }
  async function disconnect() {
    const previousToken = token
    generation.current += 1
    const endedAt = generation.current
    void client.cancelQueries()
    client.clear()
    setToken('')
    setSignOutNotice('')
    if (authMode === 'password') {
      try { await accountApi.logout(previousToken) }
      catch { if (generation.current === endedAt) setSignOutNotice('Signed out on this browser. Server sign-out could not be confirmed; that session remains valid until revoked or expired.') }
    }
  }
  return (
    <QueryClientProvider client={client}>
      <header className="flex items-center gap-4 border-b border-line bg-white px-[max(1.25rem,calc((100vw_-_1080px)/2))] py-4 max-[600px]:flex-wrap">
        <Link to="/" className="text-xl font-extrabold no-underline">
          ResolveFlow
        </Link>
        <span className="mr-auto text-[0.85rem] text-muted">
          {support ? 'Support demo' : 'Customer demo'}
        </span>
        <Link to={support ? '/reports' : '/support'}>
          {support ? 'Customer reports' : 'Support timeline'}
        </Link>
        {token && (
          <button
            className="button-secondary max-[600px]:px-2.5 max-[600px]:py-2 max-[600px]:text-[0.8rem]"
            onClick={() => void disconnect()}
          >
            End session
          </button>
        )}
      </header>
      <main className="mx-auto max-w-[960px] px-5 pt-12 pb-20 max-[600px]:pt-8">
        {!token ? (
          <section className="card mx-auto my-12 max-w-[580px] border-line">
            <p className="eyebrow">
              {support ? 'Internal support' : 'My reports'}
            </p>
            <h1>
              {support
                ? 'Review saved execution.'
                : 'Keep support in the loop.'}
            </h1>
            <p>
              {support
                ? 'Inspect execution history for reports your support identity can access.'
                : 'Submit a problem, review your reports, and update the affected service.'}
            </p>
            {signOutNotice && <p role="status" className="notice">{signOutNotice}</p>}
            {authMode === 'password' ? <AccountForm experience={experience} onConnect={(value) => {
              generation.current += 1
              setToken(value)
              setSignOutNotice('')
            }} /> : <form onSubmit={connect}>
              <label className="form-label" htmlFor="demo-token">
                Demo {experience} token
              </label>
              <input
                className="form-field"
                id="demo-token"
                type="password"
                autoComplete="off"
                value={enteredToken}
                onChange={(e) => setEnteredToken(e.target.value)}
                required
              />
              <p className="hint">
                Use a configured demo {experience} identity. Your token stays in
                memory until you end the session or reload this page.
              </p>
              <button className="button-primary" type="submit">
                {support ? 'Open support timeline' : 'Open my reports'}
              </button>
            </form>}
          </section>
        ) : (
          <SessionContext.Provider
            value={{
              token,
              isCurrent: () => generation.current === sessionGeneration,
            }}
          >
            <div key={token}>{children}</div>
          </SessionContext.Provider>
        )}
      </main>
    </QueryClientProvider>
  )
}
