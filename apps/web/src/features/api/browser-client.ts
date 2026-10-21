import { createApiClient } from '@resolve-flow/api-client'

// Cookie sessions use a public, per-login cache key in place of a bearer token.
export const COOKIE_SESSION_PREFIX = 'cookie:'
export const SESSION_ENDED_EVENT = 'resolveflow:session-ended'
export function isCookieSession(session: string) {
  return session.startsWith(COOKIE_SESSION_PREFIX)
}
export function apiBaseUrl(session: string) {
  return isCookieSession(session)
    ? `${globalThis.location?.origin ?? 'http://localhost:3000'}/api`
    : import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
}
export function sessionHeaders(session: string): Record<string, string> {
  return isCookieSession(session)
    ? { 'X-ResolveFlow-Request': '1', 'X-ResolveFlow-Session': session.slice(COOKIE_SESSION_PREFIX.length).split(':')[0] }
    : { Authorization: `Bearer ${session}` }
}
export function sessionEnded(session: string, status: number) {
  if (isCookieSession(session) && status === 401 && typeof window !== 'undefined')
    window.dispatchEvent(new CustomEvent(SESSION_ENDED_EVENT, { detail: session }))
}
export function browserApiClient(session: string) {
  const client = createApiClient(apiBaseUrl(session))
  client.use({ onResponse({ response }) { sessionEnded(session, response.status) } })
  return client
}
