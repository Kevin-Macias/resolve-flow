// @vitest-environment node
import { createHash } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { proxyApi } from './api-proxy'

const token = `rfs_${'a'.repeat(43)}`
const sessionId = createHash('sha256').update(token).digest('hex')
const origin = 'https://web.example.com'
const upstreamOrigin = 'https://api.example.com'
const view = {
  expires_at: new Date(Date.now() + 3_600_000).toISOString(),
  user: { id: '11111111-1111-4111-8111-111111111111', email: 'person@example.com', name: 'Test', last_name: 'User', user_type: 'customer', customer_account_id: '22222222-2222-4222-8222-222222222222', is_admin: false },
}
const issued = { ...view, access_token: token, token_type: 'bearer' }
function request(path: string, method = 'GET', headers: Record<string, string> = {}, body?: string) {
  return new Request(`${origin}/api${path}`, { method, body, headers: {
    Origin: origin, 'X-ResolveFlow-Request': '1', 'X-ResolveFlow-Session': sessionId,
    Cookie: `__Host-resolveflow-session=${token}`, ...headers,
  } })
}
beforeEach(() => {
  vi.stubEnv('WEB_ORIGIN', origin)
  vi.stubEnv('API_ORIGIN', upstreamOrigin)
})
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs() })

describe('Browser API boundary', () => {
  it.each(['/auth/login', '/auth/invitations/redeem'])('sets a protected host cookie and removes credentials from %s responses', async (path) => {
    const fetch = vi.fn(async () => Response.json(issued, { status: path.endsWith('redeem') ? 201 : 200 }))
    vi.stubGlobal('fetch', fetch)
    const response = await proxyApi(request(path, 'POST', { Authorization: 'Bearer injected', 'Content-Type': 'application/json' }, '{}'))
    expect(response.status).toBe(path.endsWith('redeem') ? 201 : 200)
    expect(await response.json()).toEqual({ ...view, session_id: sessionId })
    const cookie = response.headers.get('set-cookie')!
    expect(cookie).toContain(`__Host-resolveflow-session=${token}; Path=/; HttpOnly; SameSite=Lax; Secure; Expires=`)
    expect(cookie).not.toContain('Domain=')
    expect(response.headers.get('cache-control')).toBe('no-store')
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe(`${upstreamOrigin}${path}`)
    expect(new Headers(init.headers).has('cookie')).toBe(false)
    expect(new Headers(init.headers).has('authorization')).toBe(false)
  })

  it('restores public session metadata using the cookie bearer only on the server', async () => {
    const fetch = vi.fn(async () => Response.json(view))
    vi.stubGlobal('fetch', fetch)
    const response = await proxyApi(request('/auth/session', 'GET', { Authorization: 'Bearer injected' }))
    expect(await response.json()).toEqual({ ...view, session_id: sessionId })
    const [, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(new Headers(init.headers).get('authorization')).toBe(`Bearer ${token}`)
    expect(new Headers(init.headers).has('cookie')).toBe(false)
  })

  it.each([
    { Origin: 'https://attacker.example.com' },
    { Origin: '' },
    { 'X-ResolveFlow-Request': '' },
    { 'Sec-Fetch-Site': 'cross-site' },
  ] as Record<string, string>[])('rejects writes with invalid browser provenance: %o', async (headers) => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    expect((await proxyApi(request('/issue-reports/', 'POST', headers, '{}'))).status).toBe(403)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('rejects stale tab writes without clearing the new account cookie', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    const response = await proxyApi(request('/issue-reports/', 'POST', { 'X-ResolveFlow-Session': 'b'.repeat(64) }, '{}'))
    expect(response.status).toBe(401)
    expect(response.headers.get('set-cookie')).toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each(['/admin/invitations', '//attacker.example.com', '/issue-reports/%2f..%2fauth/login', '/health'])('rejects paths outside the browser API: %s', async (path) => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    expect((await proxyApi(request(path))).status).toBe(404)
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each(['', '__Host-resolveflow-session=bad', `__Host-resolveflow-session=${token}; __Host-resolveflow-session=${token}`])('requires an unambiguous valid cookie', async (cookie) => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    expect((await proxyApi(request('/auth/session', 'GET', { Cookie: cookie }))).status).toBe(401)
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each([401, 403, 429, 503])('preserves HTTP %s and retry hints; clears rejected sessions only on 401', async (status) => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ detail: 'Unavailable' }, { status, headers: { 'Retry-After': '15', 'Set-Cookie': 'injected=true' } })))
    const response = await proxyApi(request('/issue-reports/'))
    expect(response.status).toBe(status)
    expect(response.headers.get('retry-after')).toBe('15')
    expect(response.headers.get('set-cookie')).toBe(status === 401 ? '__Host-resolveflow-session=; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age=0' : null)
  })

  it.each([true, false])('clears the cookie when logout reaches the web server; API available: %s', async (available) => {
    const fetch = vi.fn(async () => { if (!available) throw new Error('private upstream error'); return new Response(null, { status: 204 }) })
    vi.stubGlobal('fetch', fetch)
    const response = await proxyApi(request('/auth/logout', 'POST'))
    expect(response.status).toBe(available ? 204 : 502)
    expect(response.headers.get('set-cookie')).toContain('Max-Age=0')
    expect(await response.text()).not.toContain('private upstream error')
  })

  it('never follows upstream redirects', async () => {
    const fetch = vi.fn(async () => new Response(null, { status: 307, headers: { Location: 'https://attacker.example.com' } }))
    vi.stubGlobal('fetch', fetch)
    const response = await proxyApi(request('/auth/login', 'POST', {}, '{}'))
    expect(response.status).toBe(502)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect((fetch.mock.calls[0] as unknown as [string, RequestInit])[1].redirect).toBe('manual')
  })

  it('rejects oversized bodies before calling the API', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    expect((await proxyApi(request('/issue-reports/', 'POST', {}, 'x'.repeat(65_537)))).status).toBe(413)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('streams events immediately, forwards resume cursors, and cancels upstream reads', async () => {
    let source!: ReadableStreamDefaultController<Uint8Array>
    const cancelled = vi.fn()
    const body = new ReadableStream<Uint8Array>({ start(controller) { source = controller }, cancel: cancelled })
    const fetch = vi.fn(async () => new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }))
    vi.stubGlobal('fetch', fetch)
    const response = await proxyApi(request('/intake-runs/11111111-1111-4111-8111-111111111111/events', 'GET', { 'Last-Event-ID': '3' }))
    const reader = response.body!.getReader()
    source.enqueue(new TextEncoder().encode(': heartbeat\n\n'))
    expect(new TextDecoder().decode((await reader.read()).value)).toBe(': heartbeat\n\n')
    expect(response.headers.get('x-accel-buffering')).toBe('no')
    const [, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(new Headers(init.headers).get('last-event-id')).toBe('3')
    await reader.cancel()
    expect(cancelled).toHaveBeenCalled()
  })

  it.each([{ ...issued, expires_at: '2000-01-01T00:00:00Z' }, { ...issued, access_token: 'bad' }])('rejects invalid issued sessions without setting a cookie', async (data) => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(data)))
    const response = await proxyApi(request('/auth/login', 'POST', {}, '{}'))
    expect(response.status).toBe(502)
    expect(response.headers.get('set-cookie')).toBeNull()
  })

  it('fails closed without production origins', async () => {
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('WEB_ORIGIN', '')
    expect((await proxyApi(request('/auth/session'))).status).toBe(503)
  })
})
