vi.mock('../metrics/metrics-panel', () => ({ MetricsPanel: () => null }))
import { act, cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { z } from 'zod'

import { SessionBoundary } from '../session/session-boundary'
import { ExecutionTimeline } from './components/execution-timeline'
import { eventSchema, supportRunSchema } from './schemas'
import { SupportHome } from './screens/support-home'
import { SupportReport } from './screens/support-report'
import rawFixture from './timeline.fixture.json?raw'

// Evidence behavior and combined-page access loss are exercised in evidence.test.tsx.
vi.mock('../evidence/evidence-panel', () => ({ EvidencePanel: () => null }))
vi.mock('../approval/action-panel', () => ({ ActionPanel: () => null }))

// Serialized by the actual Python SupportRun/ExecutionEvent models.
const fixture = z
  .object({ run: supportRunSchema, approval: z.array(eventSchema) })
  .parse(JSON.parse(rawFixture))
const run = fixture.run
const id = run.report_id
const otherId = '33333333-3333-4333-8333-333333333333'

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mount(path = `/support/reports/${id}`) {
  vi.stubGlobal('scrollTo', vi.fn())
  const root = createRootRoute({
    component: () => (
      <SessionBoundary>
        <Outlet />
      </SessionBoundary>
    ),
  })
  const home = createRoute({
    getParentRoute: () => root,
    path: '/support/',
    component: SupportHome,
  })
  const report = createRoute({
    getParentRoute: () => root,
    path: '/support/reports/$reportId',
    component: () => <SupportReport reportId={report.useParams().reportId} />,
  })
  const customer = createRoute({
    getParentRoute: () => root,
    path: '/reports/',
    component: () => <h1>Customer reports</h1>,
  })
  const router = createRouter({
    routeTree: root.addChildren([home, report, customer]),
    history: createMemoryHistory({ initialEntries: [path] }),
  })
  render(<RouterProvider router={router} />)
  return { user: userEvent.setup(), router }
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
})

describe('saved event presentation', () => {
  it('preserves saved stage/sequence order despite earlier clock timestamps and explains outcomes', () => {
    render(
      <ExecutionTimeline events={[...run.timeline, ...fixture.approval]} />,
    )
    const rows = within(
      screen.getByRole('list', { name: 'Saved execution events' }),
    ).getAllByRole('listitem')
    expect(
      rows.map((row) => within(row).getByRole('heading').textContent),
    ).toEqual([
      'Intake started',
      'Continued with incomplete context',
      'Intake report prepared',
      'Action approved',
      'Tool execution succeeded',
      'Tool execution failed',
    ])
    expect(rows[0].querySelector('time')?.dateTime).toBe(
      run.timeline[0].occurred_at,
    )
    expect(rows[0].querySelector('time')?.textContent).toBe(
      run.timeline[0].occurred_at,
    )
    expect(screen.getByText('Missing information')).toBeTruthy()
    expect(
      screen.getAllByText('Continued with incomplete context.'),
    ).toHaveLength(2)
    expect(
      screen.getByText(/This does not mean a support ticket was created/),
    ).toBeTruthy()
    expect(
      screen.getByText(
        'The decision was saved. Tool execution is a separate outcome.',
      ),
    ).toBeTruthy()
    expect(
      screen.getByText(
        'Simulated outcome. No real support ticket was created.',
      ),
    ).toBeTruthy()
    expect(screen.getByText(/The effect is unknown/)).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('keeps loading, empty, failed, and access-loss displays distinct', () => {
    const { rerender } = render(<ExecutionTimeline events={[]} loading />)
    expect(screen.getByText('Loading saved timeline…')).toBeTruthy()
    expect(screen.queryByText(/No saved events/)).toBeNull()
    rerender(<ExecutionTimeline events={[]} />)
    expect(screen.getByText(/No saved events yet/)).toBeTruthy()
    rerender(<ExecutionTimeline events={[]} error="Read failed" />)
    expect(screen.getByRole('alert').textContent).toBe('Read failed')
    expect(screen.queryByText(/No saved events/)).toBeNull()
    rerender(
      <ExecutionTimeline
        events={run.timeline}
        unavailable
        error="Access lost"
      />,
    )
    expect(screen.getByRole('alert').textContent).toBe('Access lost')
    expect(screen.queryByRole('list')).toBeNull()
  })
})

describe('authorized support route', () => {
  it('rejects an invalid report URL before making a request', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const { user } = mount('/support/reports/invalid')
    await connect(user)
    expect((await screen.findByRole('alert')).textContent).toBe(
      'Enter a valid report ID.',
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows an initial server failure without claiming the history is empty', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(json({ detail: 'private infrastructure detail' }, 503))
    vi.stubGlobal('fetch', fetchMock)
    const { user } = mount()
    await connect(user)
    expect((await screen.findByRole('alert')).textContent).toBe(
      'The saved timeline could not be loaded. Refresh to try again.',
    )
    expect(screen.queryByText(/No saved events/)).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('discards previously loaded history when a refreshed response is invalid', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json(run))
        .mockResolvedValue(
          json({
            ...run,
            timeline: [
              { ...run.timeline[0], event_type: 'private unknown event' },
            ],
          }),
        ),
    )
    const { user } = mount()
    await connect(user)
    await screen.findByText('Intake started')
    await user.click(screen.getByRole('button', { name: 'Refresh timeline' }))
    await screen.findByRole('alert')
    expect(screen.queryByRole('list')).toBeNull()
    expect(screen.queryByText('private unknown event')).toBeNull()
  })

  it('validates a report ID locally, then reads only the support endpoint and replaces repeated reads', async () => {
    const requests: Request[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        requests.push(request)
        return json(run)
      }),
    )
    const { user } = mount('/support/')
    await connect(user)
    await user.type(screen.getByLabelText('Report ID'), 'invalid')
    await user.click(screen.getByRole('button', { name: 'Open timeline' }))
    expect(screen.getByRole('alert').textContent).toBe(
      'Enter a valid report ID.',
    )
    expect(requests).toHaveLength(0)
    await user.clear(screen.getByLabelText('Report ID'))
    await user.type(screen.getByLabelText('Report ID'), id)
    await user.click(screen.getByRole('button', { name: 'Open timeline' }))
    await screen.findByText('Intake started')
    await user.click(screen.getByRole('button', { name: 'Refresh timeline' }))
    await screen.findByRole('button', { name: 'Refresh timeline' })
    expect(screen.getAllByRole('listitem')).toHaveLength(run.timeline.length)
    expect(requests).toHaveLength(2)
    for (const request of requests) {
      expect(request.method).toBe('GET')
      expect(new URL(request.url).pathname).toBe(
        `/support/issue-reports/${id}/intake-run`,
      )
      expect(request.headers.get('Authorization')).toBe('Bearer support-one')
    }
    expect(screen.getByText(/Offline simulation/)).toBeTruthy()
  })

  it('shows loading before the first read, and an empty saved run without claiming analysis has not started', async () => {
    let finish!: (value: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve
          }),
      ),
    )
    const { user } = mount()
    await connect(user)
    await screen.findByText('Loading saved timeline…')
    await act(async () => {
      finish(json({ ...run, timeline: [], operation_pending: true }))
    })
    await screen.findByText(/No saved events yet/)
    expect(screen.getByText(/An accepted operation is pending/)).toBeTruthy()
    expect(screen.queryByText(/analysis has not started/i)).toBeNull()
  })

  it('retains history with a stale notice during transient failure, then clears the notice after refresh', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json(run))
        .mockRejectedValueOnce(new TypeError('private connection detail'))
        .mockResolvedValue(json(run)),
    )
    const { user } = mount()
    await connect(user)
    await screen.findByText('Intake started')
    await user.click(screen.getByRole('button', { name: 'Refresh timeline' }))
    await screen.findByText(/Showing the last loaded history/)
    expect(screen.getByText('Intake started')).toBeTruthy()
    expect(screen.queryByText('private connection detail')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Refresh timeline' }))
    await screen.findByRole('button', { name: 'Refresh timeline' })
    expect(screen.queryByText(/Showing the last loaded history/)).toBeNull()
  })

  it.each([401, 403, 404])(
    'removes cached history after HTTP %s and does not infer archival or no run',
    async (status) => {
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockResolvedValueOnce(json(run))
          .mockResolvedValue(json({ detail: 'private denial detail' }, status)),
      )
      const { user } = mount()
      await connect(user)
      await screen.findByText('Intake started')
      await user.click(screen.getByRole('button', { name: 'Refresh timeline' }))
      await screen.findByRole('alert')
      expect(screen.queryByRole('list')).toBeNull()
      expect(screen.queryByText(/Offline simulation/)).toBeNull()
      expect(screen.getByRole('alert').textContent).not.toMatch(
        /private|archived|not started/,
      )
    },
  )

  it.each([
    { ...run, report_id: otherId },
    { ...run, simulated: false },
    { ...run, timeline: [...run.timeline, run.timeline[0]] },
    { ...run, timeline: [{ ...run.timeline[0], workflow_run_id: otherId }] },
    { ...run, timeline: [{ ...run.timeline[0], sequence: 2 }] },
    { ...run, timeline: fixture.approval },
    {
      ...run,
      timeline: [
        {
          ...run.timeline[0],
          metadata: { reasons: [], secret: 'private text' },
        },
      ],
    },
    {
      ...run,
      timeline: [{ ...run.timeline[0], occurred_at: '2026-10-12T12:00:00' }],
    },
  ])(
    'rejects inconsistent successful history without exposing it',
    async (invalid) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(invalid)))
      const { user } = mount()
      await connect(user)
      expect((await screen.findByRole('alert')).textContent).toBe(
        'ResolveFlow returned an invalid timeline response. Refresh to try again.',
      )
      expect(screen.queryByRole('list')).toBeNull()
      expect(screen.queryByText('private text')).toBeNull()
    },
  )

  it('removes the previous report immediately when navigating to another report with a pending read', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json(run))
        .mockImplementation(() => new Promise(() => {})),
    )
    const { user, router } = mount()
    await connect(user)
    await screen.findByText('Intake started')
    await act(async () => {
      await router.navigate({
        to: '/support/reports/$reportId',
        params: { reportId: otherId },
      })
    })
    await screen.findByText('Loading saved timeline…')
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('cancels pending reads on session exit and ignores late results after identity change', async () => {
    let finish!: (value: Response) => void
    let firstRequest!: Request
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementationOnce((request: Request) => {
          firstRequest = request
          return new Promise<Response>((resolve) => {
            finish = resolve
          })
        })
        .mockResolvedValue(json({ detail: 'Unavailable' }, 404)),
    )
    const { user } = mount()
    await connect(user)
    await screen.findByText('Loading saved timeline…')
    await user.click(screen.getByRole('button', { name: 'End session' }))
    expect(firstRequest.signal.aborted).toBe(true)
    await connect(user, 'support-two')
    await screen.findByRole('alert')
    await act(async () => {
      finish(json(run))
    })
    expect(screen.queryByRole('list')).toBeNull()
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })

  it('requires a separate customer session when leaving support', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(run)))
    const { user } = mount()
    await connect(user)
    await screen.findByText('Intake started')
    await user.click(screen.getByRole('link', { name: 'Customer reports' }))
    await screen.findByLabelText('Demo customer token')
    expect(screen.queryByRole('list')).toBeNull()
    expect(
      screen.queryByRole('heading', { name: 'Customer reports' }),
    ).toBeNull()
  })
})
