import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, Outlet, RouterProvider } from '@tanstack/react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useEffect } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'

import { SessionBoundary } from './session-boundary'
import { useSessionToken } from './workspace-session'

const token = `rfs_${'a'.repeat(43)}`
const password = 'Correct horse battery staple.'
function session(role: 'customer' | 'support' = 'customer') {
  return {
    access_token: token, token_type: 'bearer', expires_at: new Date(Date.now() + 3_600_000).toISOString(),
    user: { id: '11111111-1111-4111-8111-111111111111', email: 'person@example.com', name: 'Invited', last_name: 'Person', user_type: role, customer_account_id: role === 'customer' ? '22222222-2222-4222-8222-222222222222' : null, is_admin: false },
  }
}
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } }) }
function mount(experience: 'customer' | 'support' = 'customer', initialPath?: string) {
  const opened = vi.fn()
  const caches: QueryClient[] = []
  function PrivatePage({ role }: { role: 'customer' | 'support' }) {
    const sessionToken = useSessionToken()
    const client = useQueryClient()
    useEffect(() => { opened(role, sessionToken); caches.push(client) }, [role, sessionToken, client])
    return <h2>{role === 'customer' ? 'Private reports' : 'Private support'}</h2>
  }
  const root = createRootRoute({ component: () => <SessionBoundary authMode="password"><Outlet /></SessionBoundary> })
  const customer = createRoute({ getParentRoute: () => root, path: '/reports/', component: () => <PrivatePage role="customer" /> })
  const support = createRoute({ getParentRoute: () => root, path: '/support/', component: () => <PrivatePage role="support" /> })
  const detail = createRoute({ getParentRoute: () => root, path: '/reports/$reportId', component: () => <PrivatePage role="customer" /> })
  const router = createRouter({ routeTree: root.addChildren([customer, support, detail]), history: createMemoryHistory({ initialEntries: [initialPath ?? (experience === 'support' ? '/support/' : '/reports/')] }) })
  return { ...render(<RouterProvider router={router} />), user: userEvent.setup(), router, opened, caches }
}
async function login(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText('Email'), 'PERSON@example.com')
  await user.type(screen.getByLabelText('Password'), password)
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })

describe('Permanent invitation accounts', () => {
  it('opens an email draft to request an invitation when a contact address is configured', async () => {
    vi.stubEnv('VITE_INVITATION_EMAIL', 'invitations@example.com')
    mount()
    const link = await screen.findByRole('link', { name: 'Request an invitation' })
    expect(decodeURIComponent(link.getAttribute('href') ?? '')).toBe('mailto:invitations@example.com?subject=ResolveFlow invitation request')
  })

  it.each([
    ['customer', 'Keep support in the loop.', '/support'],
    ['support', 'Your support workspace.', '/reports'],
  ] as const)('shows the %s entry page without a workspace header', async (experience, title, alternatePath) => {
    mount(experience)
    expect(await screen.findByRole('heading', { name: title })).toBeDefined()
    expect(screen.queryByRole('banner')).toBeNull()
    expect(screen.queryByRole('button', { name: 'End session' })).toBeNull()
    expect(screen.getAllByRole('link').some((link) => link.getAttribute('href') === alternatePath)).toBe(true)
    expect(screen.getByLabelText('Email')).toBeDefined()
  })

  it('signs in with email/password and revokes the session on sign-out', async () => {
    const calls: Request[] = []
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      calls.push(request)
      return request.url.endsWith('/auth/logout') ? new Response(null, { status: 204 }) : json(session())
    }))
    const { user } = mount()
    await login(user)
    expect(await screen.findByText('Private reports')).toBeDefined()
    expect(screen.getByRole('banner')).toBeDefined()
    expect(await calls[0].json()).toEqual({ email: 'person@example.com', password })
    await user.click(screen.getByRole('button', { name: 'End session' }))
    expect(await screen.findByLabelText('Email')).toBeDefined()
    expect(screen.queryByRole('banner')).toBeNull()
    await waitFor(() => expect(calls.length).toBe(2))
    expect(calls[1].method).toBe('POST')
    expect(calls[1].headers.get('Authorization')).toBe(`Bearer ${token}`)
  })

  it('accepts an invitation without asking the recipient to choose permissions', async () => {
    let submitted: unknown
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      expect(request.url.endsWith('/auth/invitations/redeem')).toBe(true)
      submitted = await request.json()
      return json(session(), 201)
    }))
    const { user } = mount()
    await user.click(await screen.findByRole('button', { name: 'Have an invitation?' }))
    await user.type(screen.getByLabelText('Invitation token'), 'rfi_invitation')
    await user.type(screen.getByLabelText('First name'), 'Invited')
    await user.type(screen.getByLabelText('Last name'), 'Person')
    await user.type(screen.getByLabelText('Password'), password)
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Private reports')).toBeDefined()
    expect(submitted).toEqual({ token: 'rfi_invitation', name: 'Invited', last_name: 'Person', password })
  })

  it.each([401, 429])('shows a safe sign-in error for HTTP %s without retrying', async (status) => {
    const fetch = vi.fn(async () => json({}, status))
    vi.stubGlobal('fetch', fetch)
    const { user } = mount()
    await login(user)
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(screen.queryByText('Private reports')).toBeNull()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('alert').textContent).not.toContain(password)
  })

  it('rejects an inconsistent session response', async () => {
    const invalid = session()
    invalid.user.is_admin = true
    vi.stubGlobal('fetch', vi.fn(async () => json(invalid)))
    const { user } = mount()
    await login(user)
    expect((await screen.findByRole('alert')).textContent).toContain('invalid session')
    expect(screen.queryByText('Private reports')).toBeNull()
  })

  it.each([
    ['customer', 'support', 'Private support', '/support'],
    ['support', 'customer', 'Private reports', '/reports'],
    ['customer', 'customer', 'Private reports', '/reports'],
    ['support', 'support', 'Private support', '/support'],
  ] as const)('routes a %s entry sign-in to the authenticated %s workspace', async (entry, role, heading, destination) => {
    const fetch = vi.fn(async (request: Request) => request.url.endsWith('/auth/logout')
      ? new Response(null, { status: 204 }) : json(session(role)))
    vi.stubGlobal('fetch', fetch)
    const { user, router, opened } = mount(entry)
    await login(user)
    expect(await screen.findByRole('heading', { name: heading })).toBeDefined()
    expect(router.state.location.pathname.replace(/\/$/, '')).toBe(destination)
    expect(screen.queryByRole('alert')).toBeNull()
    expect(opened.mock.calls).toEqual([[role, token]])
    expect(fetch).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'End session' }))
    await screen.findByLabelText('Email')
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(fetch.mock.calls[1][0].url).toContain('/auth/logout')
  })

  it.each([
    ['customer', 'support', 'Private support'],
    ['support', 'customer', 'Private reports'],
  ] as const)('accepts a %s page invitation for a %s account and opens its workspace', async (entry, role, heading) => {
    const fetch = vi.fn(async () => json(session(role), 201))
    vi.stubGlobal('fetch', fetch)
    const { user, opened } = mount(entry)
    await user.click(await screen.findByRole('button', { name: 'Have an invitation?' }))
    await user.type(screen.getByLabelText('Invitation token'), 'rfi_invitation')
    await user.type(screen.getByLabelText('First name'), 'Invited')
    await user.type(screen.getByLabelText('Last name'), 'Person')
    await user.type(screen.getByLabelText('Password'), password)
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    await screen.findByRole('heading', { name: heading })
    expect(opened.mock.calls).toEqual([[role, token]])
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('clears cached customer data before signing in to a different account', async () => {
    let activeRole: 'customer' | 'support' = 'customer'
    const nextToken = `rfs_${'b'.repeat(43)}`
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => request.url.endsWith('/auth/logout')
      ? new Response(null, { status: 204 })
      : json({ ...session(activeRole), access_token: activeRole === 'customer' ? token : nextToken })))
    const { user, caches, opened } = mount()
    await login(user)
    await screen.findByText('Private reports')
    caches[0].setQueryData(['private-report'], { description: 'Customer-only observation' })
    await user.click(screen.getByRole('button', { name: 'End session' }))
    await screen.findByLabelText('Email')
    expect(caches[0].getQueryCache().getAll()).toHaveLength(0)
    activeRole = 'support'
    await login(user)
    await screen.findByText('Private support')
    expect(caches.at(-1)?.getQueryData(['private-report'])).toBeUndefined()
    expect(opened.mock.calls).toEqual([['customer', token], ['support', nextToken]])
  })

  it('revokes a late login response after switching entry pages', async () => {
    let finish!: (value: Response) => void
    const pending = new Promise<Response>((resolve) => { finish = resolve })
    const fetch = vi.fn((request: Request) => request.url.endsWith('/auth/logout')
      ? Promise.resolve(new Response(null, { status: 204 })) : pending)
    vi.stubGlobal('fetch', fetch)
    const { user, router, opened } = mount()
    await login(user)
    await act(async () => { await router.navigate({ to: '/support' }) })
    await screen.findByRole('heading', { name: 'Your support workspace.' })
    await act(async () => { finish(json(session())); await pending })
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(fetch.mock.calls[1][0].url).toContain('/auth/logout')
    expect(opened).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Email')).toBeDefined()
  })

  it('keeps a customer report deep link after matching sign-in', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(session())))
    const path = '/reports/11111111-1111-4111-8111-111111111111'
    const { user, router } = mount('customer', path)
    await login(user)
    await screen.findByText('Private reports')
    expect(router.state.location.pathname).toBe(path)
  })

  it('keeps an authenticated support session in support when navigating to a customer URL', async () => {
    const fetch = vi.fn(async () => json(session('support')))
    vi.stubGlobal('fetch', fetch)
    const { user, router, opened } = mount('support')
    await login(user)
    await screen.findByText('Private support')
    await act(async () => { await router.navigate({ to: '/reports' }) })
    await waitFor(() => expect(router.state.location.pathname.replace(/\/$/, '')).toBe('/support'))
    expect(screen.queryByText('Private reports')).toBeNull()
    expect(opened.mock.calls.every(([role, value]) => role === 'support' && value === token)).toBe(true)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('revokes a session returned after the login form unmounts', async () => {
    let resolve: (value: Response) => void = () => undefined
    const pending = new Promise<Response>((done) => { resolve = done })
    const fetch = vi.fn((request: Request) => request.url.endsWith('/auth/logout') ? Promise.resolve(new Response(null, { status: 204 })) : pending)
    vi.stubGlobal('fetch', fetch)
    const { user, unmount } = mount()
    await login(user)
    unmount()
    await act(async () => { resolve(json(session())); await pending })
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  })

  it('clears local state but reports an unconfirmed server sign-out', async () => {
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      if (request.url.endsWith('/auth/logout')) throw new TypeError('Offline')
      return json(session())
    }))
    const { user } = mount()
    await login(user)
    await screen.findByText('Private reports')
    await user.click(screen.getByRole('button', { name: 'End session' }))
    expect(await screen.findByText(/Server sign-out could not be confirmed/)).toBeDefined()
    expect(screen.queryByText('Private reports')).toBeNull()
  })
})
