import createClient from 'openapi-fetch'
import type { paths } from './schema.js'

export type { components, operations, paths } from './schema.js'

/** Create a typed client for the ResolveFlow API. */
export function createApiClient(baseUrl: string) {
  return createClient<paths>({ baseUrl })
}
