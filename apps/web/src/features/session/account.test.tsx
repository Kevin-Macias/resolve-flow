import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, Outlet, RouterProvider } from '@tanstack/react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DemoSession } from './demo-session'

const token = `rfs_${'a'.repeat(43)}`
const password = 'Correct horse battery staple.'
function session(role: 'customer' | 'support' = 'customer') {
  return {
    access_token: token, token_type: 'bearer', expires_at: new Date(Date.now() + 3_600_000).toISOString(),
    user: { id: '11111111-1111-4111-8111-111111111111', email: 'person@example.com', name: 'Invited', last_name: 'Person', user_type: role, customer_account_id: role === 'customer' ? '22222222-2222-4222-8222-222222222222' : null, is_admin: false },
  }
}
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } }) }
function mount() {
  const root = createRootRoute({ component: () => <DemoSession authMode="password"><Outlet /></DemoSession> })
  const page = createRoute({ getParentRoute: () => root, path: '/reports/', component: () => <h2>Private reports</h2> })
  const router = createRouter({ routeTree: root.addChildren([page]), history: createMemoryHistory({ initialEntries: ['/reports/'] }) })
  return { ...render(<RouterProvider router={router} />), user: userEvent.setup() }
}
async function login(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText('Email'), 'PERSON@example.com')
  await user.type(screen.getByLabelText('Password'), password)
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Permanent invitation accounts', () => {
  it('signs in with email/password and revokes the session on sign-out', async () => {
    const calls: Request[] = []
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      calls.push(request)
      return request.url.endsWith('/auth/logout') ? new Response(null, { status: 204 }) : json(session())
    }))
    const { user } = mount()
    await login(user)
    expect(await screen.findByText('Private reports')).toBeDefined()
    expect(await calls[0].json()).toEqual({ email: 'person@example.com', password })
    await user.click(screen.getByRole('button', { name: 'End session' }))
    expect(await screen.findByLabelText('Email')).toBeDefined()
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

  it('does not enter the customer workspace with a support identity', async () => {
    const fetch = vi.fn(async (request: Request) => request.url.endsWith('/auth/logout') ? new Response(null, { status: 204 }) : json(session('support')))
    vi.stubGlobal('fetch', fetch)
    const { user } = mount()
    await login(user)
    expect((await screen.findByRole('alert')).textContent).toContain('support workspace')
    expect(screen.queryByText('Private reports')).toBeNull()
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
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
