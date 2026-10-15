import type { components } from '@resolve-flow/api-client'
import { z } from 'zod'

import { uuidSchema } from '../../lib/validation'

export const progressStates = [
  'processing',
  'waiting_input',
  'stage_finished',
  'stage_failed',
] as const satisfies readonly components['schemas']['CustomerSnapshot']['progress'][]

export const customerSnapshotSchema = z.strictObject({
  version: z.literal(1),
  run_id: uuidSchema,
  revision: z.number().int().min(1).max(Number.MAX_SAFE_INTEGER),
  progress: z.enum(progressStates),
  customer_update: z
    .string()
    .refine((value) => [...value].length <= 2000)
    .nullable(),
}) satisfies z.ZodType<components['schemas']['CustomerSnapshot']>

export const streamEndSchema = z.strictObject({
  version: z.literal(1),
  reason: z.enum(['waiting_input', 'stage_finished', 'stage_failed']),
})

export const streamErrorSchema = z.strictObject({
  version: z.literal(1),
  reason: z.enum(['unavailable', 'access_lost']),
})

export const eventIdSchema = z.string().refine((value) => !value.includes('\0'))
