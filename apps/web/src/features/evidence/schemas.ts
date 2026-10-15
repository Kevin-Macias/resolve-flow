import type { components } from '@resolve-flow/api-client'
import { z } from 'zod'

import { uuidSchema } from '../../lib/validation'

const text = z.string().min(1)
const positive = z.number().int().min(1).max(Number.MAX_SAFE_INTEGER)
const hash = z.string().regex(/^[0-9a-f]{64}$/)
const metadata = z
  .strictObject({
    document_id: text,
    source: z.literal('curated_repository'),
    source_path: text,
    title: text,
    document_type: z.enum([
      'runbook',
      'help_article',
      'historical_investigation',
    ]),
    service_code: text,
    version: text,
    document_date: z.iso.date(),
    access_class: z.enum(['PUBLIC', 'INTERNAL', 'CUSTOMER_ACCOUNT']),
    customer_account_id: uuidSchema.nullable().optional(),
    status: z.enum(['current', 'superseded']),
    superseded_by: text.nullable().optional(),
    fictional: z.boolean(),
  })
  .superRefine((value, ctx) => {
    if (
      (value.access_class === 'CUSTOMER_ACCOUNT') !==
        Boolean(value.customer_account_id) ||
      (value.status === 'superseded') !== Boolean(value.superseded_by)
    )
      ctx.addIssue({
        code: 'custom',
        message: 'Invalid source scope or status',
      })
  })
const location = z.discriminatedUnion('kind', [
  z
    .strictObject({
      kind: z.literal('markdown'),
      heading_path: z.array(text),
      line_start: positive,
      line_end: positive,
    })
    .refine((value) => value.line_end >= value.line_start),
  z.strictObject({ kind: z.literal('pdf'), page_number: positive }),
])
const citation = z
  .strictObject({
    citation_id: uuidSchema,
    chunk_id: uuidSchema,
    metadata,
    passage: z.strictObject({ document_id: text, version: text, location }),
    excerpt: text,
    content_hash: hash,
    metadata_hash: hash,
  })
  .refine(
    (value) =>
      value.metadata.document_id === value.passage.document_id &&
      value.metadata.version === value.passage.version,
  )
const role = z.enum(['supports', 'contradicts'])
const claim = z
  .strictObject({
    draft: z.strictObject({
      claim_id: text,
      statement: text,
      kind: z.enum(['supported', 'inference', 'missing_evidence', 'conflict']),
      explanation: text.nullable().optional(),
      references: z.array(z.strictObject({ chunk_id: uuidSchema, role })),
    }),
    citations: z.array(z.strictObject({ role, citation })),
  })
  .superRefine((value, ctx) => {
    const { draft, citations } = value
    const pairs = draft.references.map((ref) => `${ref.chunk_id}:${ref.role}`)
    if (
      new Set(pairs).size !== pairs.length ||
      citations.length !== pairs.length ||
      citations.some(
        (ref, index) => `${ref.citation.chunk_id}:${ref.role}` !== pairs[index],
      ) ||
      (draft.kind !== 'supported' && !draft.explanation) ||
      (draft.kind !== 'missing_evidence' &&
        !draft.references.some((ref) => ref.role === 'supports')) ||
      (draft.kind === 'conflict' &&
        !draft.references.some((ref) => ref.role === 'contradicts')) ||
      (!['inference', 'conflict'].includes(draft.kind) &&
        draft.references.some((ref) => ref.role === 'contradicts'))
    )
      ctx.addIssue({
        code: 'custom',
        message: 'Inconsistent claim attribution',
      })
  })

export const supportEvidenceSchema = z
  .strictObject({
    version: z.literal(1),
    report_id: uuidSchema,
    analysis_id: uuidSchema.nullable(),
    operation_id: uuidSchema.nullable(),
    status: z.enum(['absent', 'pending', 'ready', 'failed']),
    created_at: z.iso.datetime({ offset: true }).nullable(),
    provider_mode: z.enum(['offline', 'live']).nullable(),
    simulated: z.boolean(),
    input_revision: positive.nullable(),
    older_input: z.boolean(),
    passages: z
      .array(
        z.strictObject({
          citation,
          rank: positive.max(5),
          score: z.number().min(-1).max(1),
          score_metric: z.enum(['fixture', 'cosine_similarity']),
          historical: z.boolean(),
        }),
      )
      .max(5),
    report: z.strictObject({ claims: z.array(claim) }),
  })
  .superRefine((value, ctx) => {
    const present = value.status !== 'absent'
    const byChunk = new Map(
      value.passages.map((item) => [item.citation.chunk_id, item.citation]),
    )
    if (
      [
        value.analysis_id,
        value.operation_id,
        value.created_at,
        value.provider_mode,
      ].some((item) => (item !== null) !== present) ||
      value.simulated !== (value.provider_mode === 'offline') ||
      (value.status !== 'ready' &&
        (value.passages.length || value.report.claims.length)) ||
      byChunk.size !== value.passages.length ||
      new Set(value.report.claims.map((item) => item.draft.claim_id)).size !==
        value.report.claims.length ||
      value.passages.some(
        (item, index) =>
          item.rank !== index + 1 ||
          item.score_metric !==
            (value.simulated ? 'fixture' : 'cosine_similarity'),
      ) ||
      value.report.claims.some((item) =>
        item.citations.some(
          (ref) =>
            JSON.stringify(byChunk.get(ref.citation.chunk_id)) !==
            JSON.stringify(ref.citation),
        ),
      )
    )
      ctx.addIssue({
        code: 'custom',
        message: 'Invalid saved evidence binding',
      })
  }) satisfies z.ZodType<components['schemas']['SupportEvidence']>

export type SupportEvidence = z.infer<typeof supportEvidenceSchema>
