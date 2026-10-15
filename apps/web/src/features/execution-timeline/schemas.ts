import type { components } from '@resolve-flow/api-client'
import { z } from 'zod'

import { uuidSchema } from '../../lib/validation'

const integer = z.number().int().min(0).max(Number.MAX_SAFE_INTEGER)
const positive = integer.min(1)

export const metadataSchema = z.strictObject({
  round_number: integer.nullable().optional(),
  attempts: positive.nullable().optional(),
  reasons: z.array(
    z.enum([
      'missing_data',
      'contradiction',
      'low_confidence',
      'unknown_service',
      'unknown_severity',
    ]),
  ),
  question_count: integer.max(2).nullable().optional(),
  clarification_cause: z
    .enum(['questions_available', 'no_questions', 'round_limit'])
    .nullable()
    .optional(),
  extraction_failure: z
    .enum([
      'refusal',
      'empty_output',
      'malformed_json',
      'invalid_data',
      'provider_error',
    ])
    .nullable()
    .optional(),
  provider_failure: z
    .enum(['timeout', 'transient', 'permanent'])
    .nullable()
    .optional(),
  action_id: uuidSchema.nullable().optional(),
  action_version: positive.nullable().optional(),
  fingerprint: z
    .string()
    .regex(/^[0-9a-f]{64}$/)
    .nullable()
    .optional(),
  actor_id: uuidSchema.nullable().optional(),
  support_ticket_id: uuidSchema.nullable().optional(),
  outcome: z.enum(['unknown', 'simulated']).nullable().optional(),
  incomplete: z.boolean().nullable().optional(),
}) satisfies z.ZodType<components['schemas']['EventMetadata']>

export const eventSchema = z.strictObject({
  event_id: uuidSchema,
  workflow_run_id: uuidSchema,
  stage: z.enum(['intake', 'approval']),
  sequence: positive,
  occurred_at: z.iso.datetime({ offset: true }),
  event_type: z.enum([
    'workflow_started',
    'extraction_succeeded',
    'extraction_failed',
    'clarification_evaluated',
    'clarification_requested',
    'clarification_answered',
    'continued_incomplete',
    'diagnosis_prepared',
    'report_ready',
    'approval_requested',
    'action_approved',
    'action_rejected',
    'tool_succeeded',
    'tool_failed',
  ]),
  metadata: metadataSchema,
}) satisfies z.ZodType<components['schemas']['ExecutionEvent']>

export type ExecutionEvent = z.infer<typeof eventSchema>

export const supportRunSchema = z
  .strictObject({
    version: z.literal(1),
    run_id: uuidSchema,
    report_id: uuidSchema,
    provider_mode: z.enum(['offline', 'live']),
    simulated: z.boolean(),
    operation_pending: z.boolean(),
    timeline: z.array(eventSchema),
  })
  .superRefine((run, context) => {
    const ids = new Set<string>()
    if (run.simulated !== (run.provider_mode === 'offline')) {
      context.addIssue({
        code: 'custom',
        message: 'Inconsistent provider label',
      })
    }
    run.timeline.forEach((event, index) => {
      if (
        event.stage !== 'intake' ||
        event.workflow_run_id !== run.run_id ||
        event.sequence !== index + 1 ||
        ids.has(event.event_id)
      ) {
        context.addIssue({
          code: 'custom',
          path: ['timeline', index],
          message: 'Inconsistent saved history',
        })
      }
      ids.add(event.event_id)
    })
  }) satisfies z.ZodType<components['schemas']['SupportRun']>

export type SupportRun = z.infer<typeof supportRunSchema>
