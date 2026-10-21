import { z } from 'zod'

import { limitErrorMessage } from '../api/limit-errors'
import { browserApiClient, COOKIE_SESSION_PREFIX, sessionHeaders } from '../api/browser-client'
import { sessionSchema } from './session-contract'
export { sessionSchema, type AccountSession } from './session-contract'

export const loginSchema = z.strictObject({
  email: z.email().trim().toLowerCase(),
  password: z.string().min(1, 'Enter your password.').max(128),
})
export const enrollmentSchema = z.strictObject({
  email: z.email().trim().toLowerCase(),
  token: z.string().trim().min(1, 'Enter your invitation token.').max(256),
  name: z.string().trim().min(1, 'Enter your first name.').max(200),
  last_name: z.string().trim().min(1, 'Enter your last name.').max(200),
  password: z.string().min(15, 'Use at least 15 characters.').max(128),
})

function client() { return browserApiClient(COOKIE_SESSION_PREFIX) }

async function parse(data: unknown, response: Response, enroll: boolean) {
  if (!response.ok) throw new Error(
    limitErrorMessage(response.status) ?? (response.status === 401 ? 'Email or password was not accepted.'
        : response.status === 400 ? 'This invitation is invalid, expired, revoked, or already used. If you already accepted it, sign in with your email and password.'
          : response.status === 409 ? 'This email is already registered. Sign in or choose another email.'
          : response.status === 422 ? 'Check your details and password length.'
            : enroll ? 'Account setup could not be confirmed. Try signing in with the email and password you entered before accepting again.'
              : 'Sign-in is unavailable. Try again later.'),
  )
  const result = sessionSchema.safeParse(data)
  if (!result.success || Date.parse(result.data.expires_at) <= Date.now())
    throw new Error('ResolveFlow returned an invalid session. Try signing in again.')
  return result.data
}

export const accountApi = {
  async restore(signal?: AbortSignal) {
    const { data, response } = await client().GET('/auth/session', { signal })
    if (response.status === 401) return null
    return parse(data, response, false)
  },
  async login(body: z.infer<typeof loginSchema>) {
    const { data, response } = await client().POST('/auth/login', { body, headers: sessionHeaders(COOKIE_SESSION_PREFIX) })
    return parse(data, response, false)
  },
  async enroll(body: z.infer<typeof enrollmentSchema>) {
    const { data, response } = await client().POST('/auth/invitations/redeem', { body, headers: sessionHeaders(COOKIE_SESSION_PREFIX) })
    return parse(data, response, true)
  },
  async logout(session: string) {
    const { response } = await client().POST('/auth/logout', { headers: sessionHeaders(session) })
    if (!response.ok) throw new Error('Server sign-out could not be confirmed.')
  },
}
