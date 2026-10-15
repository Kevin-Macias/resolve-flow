import type { components } from '@resolve-flow/api-client'
import { z } from 'zod'

import { uuidSchema } from '../../lib/validation'
import { customerSnapshotSchema } from '../workflow-stream/schemas'

const revisionSchema = z.number().int().min(1).max(Number.MAX_SAFE_INTEGER)
const textSchema = z.string().refine((value) => {
  const length = [...value].length
  return value.trim().length > 0 && length <= 2000
}, 'Enter an answer between 1 and 2,000 characters.')
export const answerSchema = z.string().trim().pipe(textSchema)
export const answersSchema = z.array(answerSchema).min(1).max(2)

const pauseSchema = z.strictObject({
  pending_id: uuidSchema,
  round_number: z.number().int().nullable(),
  mode: z.enum(['answer_or_continue', 'continue_only']),
  cause: z.enum(['questions_available', 'no_questions', 'round_limit']),
  questions: z.array(textSchema).max(2),
}) satisfies z.ZodType<components['schemas']['CustomerPause']>

const turnSchema = z
  .strictObject({
    round_number: z.number().int().min(1).max(2),
    questions: z.array(textSchema).max(2),
    answers: z.array(textSchema).max(2),
  })
  .refine((turn) => turn.questions.length === turn.answers.length)

export const customerRunSchema = z
  .strictObject({
    version: z.literal(1),
    run_id: uuidSchema,
    report_id: uuidSchema,
    revision: revisionSchema,
    status: z.enum([
      'processing',
      'needs_clarification',
      'needs_confirmation',
      'failed',
    ]),
    provider_mode: z.enum(['offline', 'live']),
    simulated: z.boolean(),
    message: textSchema,
    operation_pending: z.boolean(),
    pending: pauseSchema.nullable(),
    turns: z.array(turnSchema).max(2),
    incomplete: z.boolean(),
    snapshot: customerSnapshotSchema,
  })
  .superRefine((run, context) => {
    const progress = {
      processing: 'processing',
      needs_clarification: 'waiting_input',
      needs_confirmation: 'stage_finished',
      failed: 'stage_failed',
    } as const
    if (
      run.snapshot.run_id !== run.run_id ||
      run.snapshot.revision !== run.revision ||
      run.snapshot.progress !== progress[run.status] ||
      run.snapshot.customer_update !== run.message ||
      run.simulated !== (run.provider_mode === 'offline') ||
      (run.pending !== null) !== (run.status === 'needs_clarification') ||
      (run.status === 'processing' && !run.operation_pending) ||
      (run.status === 'needs_clarification' && run.operation_pending)
    ) {
      context.addIssue({
        code: 'custom',
        message: 'Inconsistent customer state',
      })
    }
    if (
      run.pending &&
      ((run.pending.mode === 'answer_or_continue') !==
        run.pending.questions.length > 0 ||
        (run.pending.cause === 'questions_available') !==
          (run.pending.mode === 'answer_or_continue'))
    ) {
      context.addIssue({
        code: 'custom',
        message: 'Inconsistent clarification pause',
      })
    }
  }) satisfies z.ZodType<components['schemas']['CustomerRun']>

export type CustomerRun = z.infer<typeof customerRunSchema>
export type ClarificationRequest = components['schemas']['ClarificationRequest']
