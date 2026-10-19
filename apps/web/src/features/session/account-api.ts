import { limitErrorMessage } from '../api/limit-errors'
import { createApiClient } from '@resolve-flow/api-client'
import { z } from 'zod'

export const loginSchema = z.strictObject({
  email: z.email().trim().toLowerCase(),
  password: z.string().min(1, 'Enter your password.').max(128),
})
export const enrollmentSchema = z.strictObject({
  token: z.string().trim().min(1, 'Enter your invitation token.').max(256),
  name: z.string().trim().min(1, 'Enter your first name.').max(200),
  last_name: z.string().trim().min(1, 'Enter your last name.').max(200),
  password: z.string().min(15, 'Use at least 15 characters.').max(128),
})
export const sessionSchema = z.strictObject({
  access_token: z.string().regex(/^rfs_[A-Za-z0-9_-]{43}$/),
  token_type: z.literal('bearer'),
  expires_at: z.iso.datetime({ offset: true }),
  user: z.strictObject({
    id: z.uuid(), email: z.email(), name: z.string(), last_name: z.string(),
    user_type: z.enum(['customer', 'support']),
    customer_account_id: z.uuid().nullable(), is_admin: z.boolean(),
  }).superRefine((user, ctx) => {
    if ((user.user_type === 'customer') !== (user.customer_account_id !== null) || (user.is_admin && user.user_type !== 'support'))
      ctx.addIssue({ code: 'custom', message: 'Invalid account scope.' })
  }),
})
export type AccountSession = z.infer<typeof sessionSchema>

function client() {
  return createApiClient(import.meta.env.VITE_API_URL ?? 'http://localhost:8000')
}

async function parse(data: unknown, response: Response, enroll: boolean) {
  if (!response.ok) throw new Error(
    limitErrorMessage(response.status) ?? (response.status === 401 ? 'Email or password was not accepted.'
        : response.status === 400 ? 'This invitation is invalid, expired, revoked, or already used. If you already accepted it, sign in with your email and password.'
          : response.status === 422 ? 'Check your details and password length.'
            : enroll ? 'Account setup could not be confirmed. Try signing in with your invited email and password before accepting again.'
              : 'Sign-in is unavailable. Try again later.'),
  )
  const result = sessionSchema.safeParse(data)
  if (!result.success || Date.parse(result.data.expires_at) <= Date.now())
    throw new Error('ResolveFlow returned an invalid session. Try signing in again.')
  return result.data
}

export const accountApi = {
  async login(body: z.infer<typeof loginSchema>) {
    const { data, response } = await client().POST('/auth/login', { body })
    return parse(data, response, false)
  },
  async enroll(body: z.infer<typeof enrollmentSchema>) {
    const { data, response } = await client().POST('/auth/invitations/redeem', { body })
    return parse(data, response, true)
  },
  async logout(token: string) {
    const { response } = await client().POST('/auth/logout', { headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok) throw new Error('Server sign-out could not be confirmed.')
  },
}
