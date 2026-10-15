import { z } from 'zod'

const descriptionMessage = 'Enter a description between 1 and 5,000 characters.'
const serviceCodeSchema = z
  .string()
  .trim()
  .transform((value) => value || null)

export const createReportSchema = z.strictObject({
  description: z
    .string()
    .trim()
    .min(1, descriptionMessage)
    .max(5000, descriptionMessage),
  affected_service_code: serviceCodeSchema,
})

export const updateReportSchema = createReportSchema.pick({
  affected_service_code: true,
})

export const demoTokenSchema = z.string().trim().min(1)
