import type { components } from '@resolve-flow/api-client'
import { z } from 'zod'

import { uuidSchema } from '../../lib/validation'
import { eventSchema } from '../execution-timeline/schemas'

const positive = z.number().int().min(1).max(Number.MAX_SAFE_INTEGER)
const fingerprint = z.string().regex(/^[0-9a-f]{64}$/)
const text = z.string().refine((value) => value.trim().length > 0)
const bounded = (max: number) =>
  z
    .string()
    .trim()
    .refine(
      (value) => value.length > 0 && [...value].length <= max,
      `Enter between 1 and ${max.toLocaleString()} characters.`,
    )
const severity = z.enum(['low', 'medium', 'high', 'critical'])
export const proposalFieldsSchema = z.strictObject({
  title: bounded(200),
  description: bounded(5000),
  service_code: bounded(100).nullable(),
  severity: severity.nullable(),
  explanation: bounded(2000),
})
export type ProposalFields = z.infer<typeof proposalFieldsSchema>
export const proposalRequestSchema = proposalFieldsSchema.extend({
  operation_id: uuidSchema,
  expected_fingerprint: fingerprint.nullable(),
}) satisfies z.ZodType<components['schemas']['ProposalRequest']>
export type ProposalRequest = z.infer<typeof proposalRequestSchema>
const proposalSchema = z.strictObject({
  action_id: uuidSchema,
  version: positive,
  idempotency_key: uuidSchema,
  tool: z.literal('create_ticket'),
  arguments: z.strictObject({
    issue_report_id: uuidSchema,
    title: text,
    description: text,
    service_code: text.nullable(),
    severity: severity.nullable(),
  }),
  explanation: text,
  expected_effect: text,
  risk: z.strictObject({
    level: z.enum(['low', 'medium', 'high']),
    reason: text,
  }),
})
export const decisionRequestSchema = z.strictObject({
  action_id: uuidSchema,
  version: positive,
  fingerprint,
  decision: z.enum(['approve', 'reject']),
}) satisfies z.ZodType<components['schemas']['ApprovalReply']>
export type DecisionRequest = z.infer<typeof decisionRequestSchema>
const decisionSchema = decisionRequestSchema.extend({
  actor_id: uuidSchema,
  decided_at: z.iso.datetime({ offset: true }),
})
const resultBinding = z.strictObject({
  action_id: uuidSchema,
  version: positive,
  fingerprint,
  idempotency_key: uuidSchema,
})
const executionSchema = resultBinding.extend({
  executed_by_user_id: uuidSchema,
  result: z.strictObject({
    support_ticket_id: uuidSchema,
    status: z.literal('open'),
    simulated: z.literal(true),
  }),
})
const failureSchema = resultBinding.extend({
  reason: z.literal('tool_failed'),
  outcome: z.literal('unknown'),
})

export const supportActionSchema = z
  .strictObject({
    version: z.literal(1),
    report_id: uuidSchema,
    run_id: uuidSchema.nullable(),
    status: z.enum([
      'absent',
      'preparing',
      'awaiting_decision',
      'rejected',
      'approved_unconfirmed',
      'simulated_success',
      'execution_unknown',
    ]),
    archived: z.boolean(),
    input_stale: z.boolean(),
    can_prepare: z.boolean(),
    proposal: proposalSchema.nullable(),
    fingerprint: fingerprint.nullable(),
    preparation_id: uuidSchema.nullable(),
    pending_preparation: proposalRequestSchema.nullable(),
    decision: decisionSchema.nullable(),
    execution: executionSchema.nullable(),
    failure: failureSchema.nullable(),
    timeline: z.array(eventSchema),
  })
  .superRefine((view, ctx) => {
    const p = view.proposal
    let invalid = false
    if (!p) {
      invalid =
        view.status !== 'absent' ||
        Boolean(
          view.fingerprint ||
          view.preparation_id ||
          view.pending_preparation ||
          view.decision ||
          view.execution ||
          view.failure ||
          view.timeline.length ||
          view.input_stale,
        )
    } else {
      invalid =
        !view.run_id ||
        !view.preparation_id ||
        !view.fingerprint ||
        p.arguments.issue_report_id !== view.report_id ||
        view.status === 'absent' ||
        (view.status === 'preparing') !== Boolean(view.pending_preparation) ||
        (view.can_prepare &&
          (view.archived || view.status !== 'awaiting_decision')) ||
        Boolean(view.execution && view.failure)
      const expected = view.pending_preparation
        ? 'preparing'
        : !view.decision
          ? 'awaiting_decision'
          : view.decision.decision === 'reject'
            ? 'rejected'
            : view.execution
              ? 'simulated_success'
              : view.failure
                ? 'execution_unknown'
                : 'approved_unconfirmed'
      invalid ||=
        view.status !== expected ||
        (view.status === 'preparing' &&
          Boolean(view.decision || view.timeline.length))
      for (const bound of [view.decision, view.execution, view.failure]) {
        if (bound)
          invalid ||=
            bound.action_id !== p.action_id ||
            bound.version !== p.version ||
            bound.fingerprint !== view.fingerprint
      }
      for (const outcome of [view.execution, view.failure]) {
        if (outcome)
          invalid ||=
            outcome.idempotency_key !== p.idempotency_key ||
            view.decision?.decision !== 'approve'
      }
    }
    const ids = new Set<string>()
    invalid ||= view.can_prepare && (view.archived || !view.run_id)
    view.timeline.forEach((event, index) => {
      invalid ||=
        event.stage !== 'approval' ||
        event.workflow_run_id !== view.run_id ||
        event.sequence !== index + 1 ||
        ids.has(event.event_id)
      ids.add(event.event_id)
    })
    if (invalid)
      ctx.addIssue({ code: 'custom', message: 'Inconsistent saved action' })
  }) satisfies z.ZodType<components['schemas']['SupportAction']>
export type SupportAction = z.infer<typeof supportActionSchema>
