import type { components } from '@resolve-flow/api-client'
import { z } from 'zod'

import { uuidSchema } from '../../lib/validation'

export const reportResponseSchema = z.object({
  id: uuidSchema,
  customer_account_id: uuidSchema,
  description: z.string().refine((value) => {
    const length = [...value].length
    return length >= 1 && length <= 5000
  }),
  affected_service: z.object({ code: z.string(), label: z.string() }).nullable(),
  status: z.enum(['draft', 'submitted', 'in_review', 'linked', 'deleted', 'closed']),
  submitted_by: z.object({
    id: uuidSchema,
    name: z.string(),
    last_name: z.string(),
  }),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
}) satisfies z.ZodType<components['schemas']['IssueReportResponse']>

export const reportListResponseSchema = z.array(reportResponseSchema)

export class ReportResponseError extends Error {
  constructor() {
    super('ResolveFlow returned an invalid report response. Refresh and try again.')
  }
}

export function parseReportResponse<T>(schema: z.ZodType<T>, data: unknown): T {
  const result = schema.safeParse(data)
  if (!result.success) throw new ReportResponseError()
  return result.data
}
