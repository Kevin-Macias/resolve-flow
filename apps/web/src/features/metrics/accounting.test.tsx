import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, Outlet, RouterProvider } from '@tanstack/react-router'
import { afterEach, expect, it, vi } from 'vitest'
import { WorkspaceSession } from '../session/workspace-session'
import { AccountingPanel, accountingSchema } from './accounting'
import { MetricsPanel } from './metrics-panel'

const id = '11111111-1111-4111-8111-111111111111'
const attemptId = '22222222-2222-4222-8222-222222222222'
function saved() {
  const value = {
    version: 1, report_id: id, offset: 0, next_offset: null,
    totals: { attempts: 1, retries: 0, live_attempts: 1, offline_attempts: 0, unfinished_attempts: 0, missing_live_usage: 1, missing_live_cost: 1, known_live_input_tokens: 0, known_live_output_tokens: 0, known_live_total_tokens: 0, known_live_cost_usd: '0', known_live_provider_ms: 3, missing_live_latency: 0, coverage_complete: false, cost_complete: false },
    attempts: [{ id: attemptId, call_id: attemptId, parent_call_id: null, request_id: null, scope_type: 'intake', scope_id: id, operation_id: id, component: 'extraction', provider_mode: 'live', configured_model: 'saved-model', resolved_model: null, prompt_id: 'extract', prompt_version: '3', attempt: 1, outcome: 'timeout', started_at: '2026-10-18T10:00:00Z', finished_at: '2026-10-18T10:00:01Z', latency_ms: 3, usage: null, cost: null, cost_status: 'usage_unavailable' }],
  }
  return { ...value, scopes: [{ scope_type: 'intake', scope_id: id, totals: value.totals }] }
}
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } }) }
function mount(legacy = false) {
  const lost = vi.fn()
  const root = createRootRoute({ component: () => <WorkspaceSession experience="support"><Outlet /></WorkspaceSession> })
  const page = createRoute({ getParentRoute: () => root, path: '/support/reports/$reportId', component: () => legacy ? <MetricsPanel reportId={id} onAccessLost={lost} /> : <AccountingPanel reportId={id} onAccessLost={lost} /> })
  const router = createRouter({ routeTree: root.addChildren([page]), history: createMemoryHistory({ initialEntries: [`/support/reports/${id}`] }) })
  render(<RouterProvider router={router} />)
  return { user: userEvent.setup(), lost }
}
async function connect(user: ReturnType<typeof userEvent.setup>, token = 'support-one') {
  await user.type(await screen.findByLabelText('Demo support token'), token)
  await user.click(screen.getByRole('button', { name: 'Open support timeline' }))
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('labels known zero as a partial subtotal when a live timeout has unknown cost', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json(saved())))
  const { user } = mount(); await connect(user)
  expect(await screen.findByText('Known live cost subtotal (partial)')).toBeTruthy()
  expect(screen.getByText(/Earlier work has no complete attempt history/)).toBeTruthy()
  expect(screen.getByText(/1 attempts without estimates/)).toBeTruthy()
  expect(screen.queryByText('Estimated live cost')).toBeNull()
})

it('does not turn offline accounting into a zero-dollar bill', async () => {
  const value = saved(); value.totals.live_attempts = 0; value.totals.offline_attempts = 1; value.totals.missing_live_cost = 0; value.totals.missing_live_usage = 0
  value.attempts[0].provider_mode = 'offline'; value.attempts[0].cost_status = 'offline'
  vi.stubGlobal('fetch', vi.fn(async () => json(value)))
  const { user } = mount(); await connect(user)
  expect(await screen.findByText(/Offline simulation is not a measured provider bill/)).toBeTruthy()
  expect(screen.queryByText('Estimated live cost')).toBeNull()
})

it('rejects inconsistent totals instead of showing an apparently complete cost', async () => {
  const invalid = saved(); invalid.totals.cost_complete = true
  expect(accountingSchema.safeParse(invalid).success).toBe(false)
  vi.stubGlobal('fetch', vi.fn(async () => json(invalid)))
  const { user, lost } = mount(); await connect(user)
  expect((await screen.findByRole('alert')).textContent).toContain('invalid metrics')
  expect(screen.queryByText(/saved-model/)).toBeNull()
  expect(lost).not.toHaveBeenCalled()
})

it.each([401, 403, 404])('reports access loss for %s and displays no protected history', async (status) => {
  vi.stubGlobal('fetch', vi.fn(async () => json({}, status)))
  const { user, lost } = mount(); await connect(user)
  await waitFor(() => expect(lost).toHaveBeenCalled())
  expect(screen.queryByText(/saved-model/)).toBeNull()
})

it('keeps temporary read failures visibly stale and supports explicit recovery', async () => {
  let fail = false
  vi.stubGlobal('fetch', vi.fn(async () => fail ? json({}, 503) : json(saved())))
  const { user } = mount(); await connect(user)
  await screen.findByText(/saved-model/)
  fail = true; await user.click(screen.getByRole('button', { name: 'Refresh attempt history' }))
  expect(await screen.findByText(/accounting records may be stale/)).toBeTruthy()
  expect(screen.getByText(/saved-model/)).toBeTruthy()
  fail = false; await user.click(screen.getByRole('button', { name: 'Refresh attempt history' }))
  await waitFor(() => expect(screen.queryByText(/accounting records may be stale/)).toBeNull())
})

it('loads history on request while preserving the existing latest-extraction view', async () => {
  const fetch = vi.fn(async (request: Request) => request.url.includes('/model-accounting') ? json(saved()) : json({ version: 1, scope: 'latest_intake_extraction', report_id: id, run_id: null, provider_mode: null, operation_pending: false, metrics: null }))
  vi.stubGlobal('fetch', fetch)
  const { user } = mount(true); await connect(user)
  await screen.findByText('No saved extraction metrics yet.')
  expect(fetch).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole('button', { name: 'Show model attempt history' }))
  expect(await screen.findByText(/saved-model/)).toBeTruthy()
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(screen.getByText(/Latest extraction only/)).toBeTruthy()
})

it('does not show a late response after ending the session', async () => {
  let resolve: (value: Response) => void = () => undefined
  const pending = new Promise<Response>(done => { resolve = done })
  vi.stubGlobal('fetch', vi.fn(() => pending))
  const { user } = mount(); await connect(user)
  await screen.findByText('Loading model attempts…')
  await user.click(screen.getByRole('button', { name: 'End session' }))
  await act(async () => { resolve(json(saved())); await pending })
  expect(screen.queryByText(/saved-model/)).toBeNull()
  expect(screen.getByLabelText('Demo support token')).toBeTruthy()
})

it('shows a recorded zero estimate with its saved pricing version', async () => {
  const initial = saved()
  const value = {    
...initial,
    totals: { ...initial.totals, missing_live_usage: 0, missing_live_cost: 0, coverage_complete: true, cost_complete: true, known_live_provider_ms: 0 },
    attempts: [{      
...initial.attempts[0], outcome: 'response_received', latency_ms: 0,
      usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0, cached_input_tokens: 0 }, cost_status: 'available',
      cost: { usd: '0', pricing_version: 'price-v1', model: 'saved-model', rate: { provider: 'openai', model: 'saved-model', input_per_million: '0', output_per_million: '0', cached_input_per_million: '0' } },
    }],
  }
  value.scopes = [{ scope_type: 'intake', scope_id: id, totals: value.totals }]
  vi.stubGlobal('fetch', vi.fn(async () => json(value)))
  const { user } = mount(); await connect(user)
  expect(await screen.findByText('Estimated live cost')).toBeTruthy()
  expect(screen.getByText('USD 0 · pricing price-v1')).toBeTruthy()
  expect(screen.getByText('0.0 ms')).toBeTruthy()
})

it('rejects another report binding before displaying history', async () => {
  const value = saved(); value.report_id = attemptId
  vi.stubGlobal('fetch', vi.fn(async () => json(value)))
  const { user } = mount(); await connect(user)
  expect((await screen.findByRole('alert')).textContent).toContain('invalid metrics')
  expect(screen.queryByText(/saved-model/)).toBeNull()
})
