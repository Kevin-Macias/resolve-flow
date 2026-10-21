import { z } from 'zod'

export const apiSessionSchema = z.strictObject({
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
export const sessionSchema = apiSessionSchema.extend({ session_id: z.string().regex(/^[a-f0-9]{64}$/) })
export const issuedSessionSchema = apiSessionSchema.extend({
  access_token: z.string().regex(/^rfs_[A-Za-z0-9_-]{43}$/),
  token_type: z.literal('bearer'),
})
export type AccountSession = z.infer<typeof sessionSchema>
