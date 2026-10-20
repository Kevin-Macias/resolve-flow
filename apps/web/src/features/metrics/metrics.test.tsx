import { cleanup, render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import { afterEach, expect, it, vi } from 'vitest'
import { WorkspaceSession } from '../session/workspace-session'
import { SupportReport } from '../execution-timeline/screens/support-report'
import timelineFixture from '../execution-timeline/timeline.fixture.json'
const timeline = timelineFixture.run
import { MetricsPanel } from './metrics-panel'
import { supportMetricsSchema } from './schemas'

vi.mock('../evidence/evidence-panel', () => ({
  EvidencePanel: () => <p>Protected evidence</p>,
}))
vi.mock('../approval/action-panel', () => ({
  ActionPanel: () => <p>Protected action</p>,
}))
const id = timeline.report_id
const saved = {
  version: 1,
  scope: 'latest_intake_extraction',
  report_id: id,
  run_id: timeline.run_id,
  provider_mode: 'offline',
  operation_pending: false,
  metrics: {
    model: 'offline-intake-v1',
    prompt_id: 'issue_report_extraction',
    prompt_version: '3',
    attempts: 2,
    usage: { input_tokens: 0, output_tokens: 4, total_tokens: 4 },
    latency_ms: null,
    estimated_cost: null,
  },
}
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function mount(combined = false) {
  vi.stubGlobal('scrollTo', vi.fn())
  const lost = vi.fn()
  const root = createRootRoute({
    component: () => (
      <WorkspaceSession experience="support">
        <Outlet />
      </WorkspaceSession>
    ),
  })
  const page = createRoute({
    getParentRoute: () => root,
    path: '/support/reports/$reportId',
    component: () => {
      const { reportId } = page.useParams()
      return combined ? (
        <SupportReport reportId={reportId} />
      ) : (
        <MetricsPanel key={reportId} reportId={reportId} onAccessLost={lost} />
      )
    },
  })
  const router = createRouter({
    routeTree: root.addChildren([page]),
    history: createMemoryHistory({
      initialEntries: [`/support/reports/${id}`],
    }),
  })
  render(<RouterProvider router={router} />)
  return { user: userEvent.setup(), lost, router }
}
async function connect(
  user: ReturnType<typeof userEvent.setup>,
  token = 'support-one',
) {
  await user.type(await screen.findByLabelText('Demo support token'), token)
  await user.click(
    screen.getByRole('button', { name: 'Open support timeline' }),
  )
}
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

it('shows saved values, zero usage, scope, simulation, and unavailable accounting', async () => {
  const fetcher = vi.fn(async () => json(saved))
  vi.stubGlobal('fetch', fetcher)
  const { user } = mount()
  await connect(user)
  await screen.findByText('offline-intake-v1')
  expect(screen.getByText('0')).toBeTruthy()
  expect(screen.getByText('issue_report_extraction · version 3')).toBeTruthy()
  expect(screen.getAllByText('Not recorded')).toHaveLength(2)
  expect(screen.getByText('Offline simulation')).toBeTruthy()
  expect(screen.getByText(/Latest extraction only/)).toBeTruthy()
  expect(
    screen.getByText(/does not account for all retry attempts/),
  ).toBeTruthy()
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('distinguishes nullable usage from zero and labels pending work', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      json({
        ...saved,
        operation_pending: true,
        metrics: { ...saved.metrics, usage: null },
      }),
    ),
  )
  const { user } = mount()
  await connect(user)
  await screen.findByText('offline-intake-v1')
  expect(screen.getAllByText('Not recorded')).toHaveLength(5)
  expect(screen.getByText(/not the pending operation/)).toBeTruthy()
})
it.each([null, { ...saved, metrics: null }])(
  'shows empty saved state %s',
  async (value) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        json(
          value ?? {
            ...saved,
            run_id: null,
            provider_mode: null,
            metrics: null,
          },
        ),
      ),
    )
    const { user } = mount()
    await connect(user)
    await screen.findByText('No saved extraction metrics yet.')
    expect(screen.queryByText('offline-intake-v1')).toBeNull()
  },
)
it('refreshes by GET and replaces stale saved metrics after a failure', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(json(saved))
    .mockRejectedValueOnce(new TypeError('offline'))
    .mockResolvedValueOnce(
      json({ ...saved, metrics: { ...saved.metrics, model: 'new-model' } }),
    )
  vi.stubGlobal('fetch', fetcher)
  const { user } = mount()
  await connect(user)
  await screen.findByText('offline-intake-v1')
  await user.click(screen.getByRole('button', { name: 'Refresh metrics' }))
  await screen.findByText('These saved metrics may be stale.')
  expect(screen.getByText('offline-intake-v1')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: 'Refresh metrics' }))
  await screen.findByText('new-model')
  expect(screen.queryByText('These saved metrics may be stale.')).toBeNull()
  expect(
    fetcher.mock.calls.every(([request]) => request.method === 'GET'),
  ).toBe(true)
})
it.each([401, 403, 404])('clears protected view on %s', async (status) => {
  let denied = false
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) =>
      request.url.endsWith('execution-metrics')
        ? json(denied ? {} : saved, denied ? status : 200)
        : json(timeline),
    ),
  )
  const { user } = mount(true)
  await connect(user)
  await screen.findByText('offline-intake-v1')
  expect(screen.getByText('Protected evidence')).toBeTruthy()
  denied = true
  await user.click(screen.getByRole('button', { name: 'Refresh metrics' }))
  await screen.findByText('Your access to this report is no longer available.')
  expect(screen.queryByText('offline-intake-v1')).toBeNull()
  expect(screen.queryByText('Protected evidence')).toBeNull()
  expect(screen.queryByText('Protected action')).toBeNull()
})
it.each([
  { ...saved, report_id: '99999999-9999-4999-8999-999999999999' },
  { ...saved, metrics: { ...saved.metrics, attempts: -1 } },
  {
    ...saved,
    metrics: {
      ...saved.metrics,
      usage: { input_tokens: -1, output_tokens: 0, total_tokens: 0 },
    },
  },
  { ...saved, metrics: { ...saved.metrics, raw_prompt: 'private' } },
  { ...saved, run_id: null },
])('hides invalid responses', async (invalid) => {
  let body: unknown = saved
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => json(body)),
  )
  const { user } = mount()
  await connect(user)
  await screen.findByText('offline-intake-v1')
  body = invalid
  await user.click(screen.getByRole('button', { name: 'Refresh metrics' }))
  await screen.findByText(/returned invalid metrics/)
  expect(screen.queryByText('offline-intake-v1')).toBeNull()
})
it('isolates late reads after ending a session', async () => {
  let resolve!: (value: Response) => void
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Promise<Response>((r) => {
          resolve = r
        }),
    ),
  )
  const { user } = mount()
  await connect(user)
  await screen.findByText('Loading saved metrics…')
  await user.click(screen.getByRole('button', { name: 'Log out' }))
  await act(async () => {
    resolve(json(saved))
    await Promise.resolve()
  })
  expect(screen.queryByText('offline-intake-v1')).toBeNull()
  expect(screen.getByLabelText('Demo support token')).toBeTruthy()
})
it('isolates late reads after changing reports', async () => {
  let resolve!: (value: Response) => void
  const other = '99999999-9999-4999-8999-999999999999'
  vi.stubGlobal(
    'fetch',
    vi.fn((request: Request) =>
      request.url.includes(other)
        ? Promise.resolve(json({ ...saved, report_id: other, metrics: null }))
        : new Promise<Response>((r) => {
            resolve = r
          }),
    ),
  )
  const { user, router } = mount()
  await connect(user)
  await screen.findByText('Loading saved metrics…')
  await act(async () => {
    await router.navigate({
      to: '/support/reports/$reportId',
      params: { reportId: other },
    })
  })
  await screen.findByText('No saved extraction metrics yet.')
  await act(async () => {
    resolve(json(saved))
    await Promise.resolve()
  })
  await waitFor(() =>
    expect(screen.queryByText('offline-intake-v1')).toBeNull(),
  )
})
it('rejects non-integer usage and invented cost in runtime validation', () => {
  expect(
    supportMetricsSchema.safeParse({
      ...saved,
      metrics: { ...saved.metrics, estimated_cost: 0 },
    }).success,
  ).toBe(false)
  expect(
    supportMetricsSchema.safeParse({
      ...saved,
      metrics: {
        ...saved.metrics,
        usage: { input_tokens: true, output_tokens: 0, total_tokens: 0 },
      },
    }).success,
  ).toBe(false)
})

it('marks saved values stale immediately when the browser goes offline', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => json(saved)),
  )
  const { user } = mount()
  await connect(user)
  await screen.findByText('offline-intake-v1')
  const online = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
  act(() => window.dispatchEvent(new Event('offline')))
  await screen.findByText('These saved metrics may be stale.')
  expect(
    screen
      .getByRole('button', { name: 'Refresh metrics' })
      .hasAttribute('disabled'),
  ).toBe(true)
  online.mockReturnValue(true)
  act(() => window.dispatchEvent(new Event('online')))
  await waitFor(() =>
    expect(
      screen.queryByText('Connection lost. Reconnect to refresh metrics.'),
    ).toBeNull(),
  )
})
