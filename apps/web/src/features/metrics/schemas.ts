import { z } from 'zod'
import type { components } from '@resolve-flow/api-client'
import { uuidSchema } from '../../lib/validation'

const count = z.number().int().nonnegative()
export const supportMetricsSchema = z
  .strictObject({
    version: z.literal(1),
    scope: z.literal('latest_intake_extraction'),
    report_id: uuidSchema,
    run_id: uuidSchema.nullable(),
    provider_mode: z.enum(['offline', 'live']).nullable(),
    operation_pending: z.boolean(),
    metrics: z
      .strictObject({
        model: z.string().min(1),
        prompt_id: z.string().min(1),
        prompt_version: z.string().min(1),
        attempts: z.number().int().positive(),
        usage: z
          .strictObject({
            input_tokens: count,
            output_tokens: count,
            total_tokens: count,
          })
          .nullable(),
        latency_ms: z.null(),
        estimated_cost: z.null(),
      })
      .nullable(),
  })
  .superRefine((value, ctx) => {
    if (
      value.run_id === null
        ? value.provider_mode !== null ||
          value.operation_pending ||
          value.metrics !== null
        : value.provider_mode === null
    ) {
      ctx.addIssue({ code: 'custom', message: 'Inconsistent metrics run' })
    }
  })
export type SupportMetrics = z.infer<typeof supportMetricsSchema>
export type GeneratedMetrics = components['schemas']['SupportMetrics']
