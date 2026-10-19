import { describe, expect, it, vi } from 'vitest'
import { reportsApi } from '../reports/api'
import { intakeApi } from '../customer-intake/api'
import { evidenceApi } from '../evidence/api'
import { actionsApi } from '../approval/api'
import { metricsApi } from '../metrics/api'
import { supportRunsApi } from '../execution-timeline/api'
import { accountApi } from '../session/account-api'

const id = '11111111-1111-4111-8111-111111111111'

describe('request limit errors', () => {
  it.each([408, 413, 429])('shows HTTP %s clearly without retrying requests', async (status) => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ error: { message: 'private raw detail' } }), {
      status, headers: { 'Content-Type': 'application/json', 'Retry-After': '60' },
    }))
    vi.stubGlobal('fetch', fetch)
    try {
      const calls = [
        () => reportsApi('token').list(),
        () => intakeApi('token', id).start(),
        () => evidenceApi('token', id).create(id),
        () => actionsApi('token', id).read(),
        () => metricsApi('token', id).read(),
        () => supportRunsApi('token').get(id),
        () => accountApi.login({ email: 'person@example.com', password: 'password' }),
      ]
      const expected = status === 413 ? /too large/ : status === 429 ? /Too many requests/ : /took too long/
      for (const call of calls) await expect(call()).rejects.toThrow(expected)
      expect(fetch).toHaveBeenCalledTimes(calls.length)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
