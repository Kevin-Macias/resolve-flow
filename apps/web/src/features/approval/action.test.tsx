vi.mock('../metrics/metrics-panel', () => ({ MetricsPanel: () => null }))
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
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

import { DemoSession } from '../session/demo-session'
import { SupportReport } from '../execution-timeline/screens/support-report'
import timelineFixture from '../execution-timeline/timeline.fixture.json'
import evidenceFixture from '../evidence/evidence.fixture.json'
import { ActionPanel } from './action-panel'
import { supportActionSchema, type SupportAction } from './schemas'
import rawFixture from './action.fixture.json?raw'

const fixtures = Object.fromEntries(
  Object.entries(JSON.parse(rawFixture)).map(([key, value]) => [
    key,
    supportActionSchema.parse(value),
  ]),
)
const awaiting = fixtures.awaiting
const id = awaiting.report_id
const p = awaiting.proposal!
function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function mount(onLost = vi.fn(), combined = false) {
  vi.stubGlobal('scrollTo', vi.fn())
  const root = createRootRoute({
    component: () => (
      <DemoSession experience="support">
        <Outlet />
      </DemoSession>
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
        <ActionPanel key={reportId} reportId={reportId} onAccessLost={onLost} />
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
async function loaded() {
  await screen.findByText(p.arguments.title)
}
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('support action review', () => {
  it('shows the complete saved proposal and explicit null classification as text', async () => {
    const fetcher = vi.fn(async () => json(awaiting))
    vi.stubGlobal('fetch', fetcher)
    const { user } = mount()
    await connect(user)
    await loaded()
    expect(screen.getByText(p.arguments.description)).toBeTruthy()
    expect(screen.getByText('Not specified (null)')).toBeTruthy()
    expect(screen.getByText('Unknown (null)')).toBeTruthy()
    expect(screen.getByText(p.risk.reason)).toBeTruthy()
    expect(screen.getByText(p.expected_effect)).toBeTruthy()
    expect(
      screen.getByText(/Simulation has no ticket write to undo/),
    ).toBeTruthy()
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it.each(['approval', 'rejection'])(
    'confirms %s inline, focuses its heading, and cancels without a request',
    async (choice) => {
      const fetcher = vi.fn(async () => json(awaiting))
      vi.stubGlobal('fetch', fetcher)
      const { user } = mount()
      await connect(user)
      await loaded()
      const trigger = screen.getByRole('button', { name: `Review ${choice}` })
      await user.click(trigger)
      const heading = screen.getByRole('heading', {
        name:
          choice === 'approval'
            ? 'Approve version 1 and allow the simulated ticket action?'
            : 'Reject version 1? This action will not execute.',
      })
      expect(document.activeElement).toBe(heading)
      expect(document.activeElement).not.toBe(
        screen.getByRole('button', {
          name:
            choice === 'approval' ? 'Approve version 1' : 'Reject version 1',
        }),
      )
      await user.click(screen.getByRole('button', { name: 'Keep reviewing' }))
      await waitFor(() => expect(document.activeElement).toBe(trigger))
      expect(fetcher).toHaveBeenCalledTimes(1)
    },
  )

  it.each(['approve', 'reject'])(
    'sends only the exact saved binding for %s and displays the server receipt',
    async (choice) => {
      const requests: Request[] = []
      vi.stubGlobal(
        'fetch',
        vi.fn(async (request: Request) => {
          requests.push(request)
          return json(
            request.method === 'GET'
              ? awaiting
              : choice === 'approve'
                ? fixtures.success
                : fixtures.rejected,
          )
        }),
      )
      const { user } = mount()
      await connect(user)
      await loaded()
      await user.click(
        screen.getByRole('button', {
          name: choice === 'approve' ? 'Review approval' : 'Review rejection',
        }),
      )
      await user.click(
        screen.getByRole('button', {
          name: `${choice === 'approve' ? 'Approve' : 'Reject'} version 1`,
        }),
      )
      await screen.findByText(
        choice === 'approve'
          ? 'Saved decision: Approved'
          : 'Saved decision: Rejected',
      )
      const post = requests.find((request) => request.method === 'POST')!
      expect(new URL(post.url).pathname).toBe(
        `/support/issue-reports/${id}/runs/${awaiting.run_id}/decision`,
      )
      expect(await post.json()).toEqual({
        action_id: p.action_id,
        version: 1,
        fingerprint: awaiting.fingerprint,
        decision: choice,
      })
      expect(
        screen.queryByRole('button', { name: 'Review approval' }),
      ).toBeNull()
      if (choice === 'reject')
        expect(screen.getByText('This action did not execute.')).toBeTruthy()
      else
        expect(
          screen.getByText(
            'Simulation; no persisted support ticket was created.',
          ),
        ).toBeTruthy()
    },
  )

  it('prevents duplicate submissions while a decision is pending', async () => {
    let finish!: (value: Response) => void
    const fetcher = vi.fn((request: Request) =>
      request.method === 'GET'
        ? Promise.resolve(json(awaiting))
        : new Promise<Response>((resolve) => {
            finish = resolve
          }),
    )
    vi.stubGlobal('fetch', fetcher)
    const { user } = mount()
    await connect(user)
    await loaded()
    await user.click(screen.getByRole('button', { name: 'Review approval' }))
    await user.dblClick(
      screen.getByRole('button', { name: 'Approve version 1' }),
    )
    await screen.findByText('Submitting decision…')
    expect(
      fetcher.mock.calls.filter(([request]) => request.method === 'POST'),
    ).toHaveLength(1)
    await act(async () => {
      finish(json(fixtures.success))
    })
    await screen.findByText('Saved decision: Approved')
  })

  it('shows the actual first decision when another reviewer rejected first', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) =>
        json(request.method === 'GET' ? awaiting : fixtures.rejected),
      ),
    )
    const { user } = mount()
    await connect(user)
    await loaded()
    await user.click(screen.getByRole('button', { name: 'Review approval' }))
    await user.click(screen.getByRole('button', { name: 'Approve version 1' }))
    await screen.findByText('Saved decision: Rejected')
    expect(screen.queryByText('Saved decision: Approved')).toBeNull()
    expect(screen.queryByText(/Simulated ticket ID:/)).toBeNull()
  })

  it('closes confirmation when a refreshed proposal changes and requires version 2 review', async () => {
    const next = {
      ...awaiting,
      preparation_id: crypto.randomUUID(),
      fingerprint: 'a'.repeat(64),
      proposal: {
        ...p,
        version: 2,
        idempotency_key: crypto.randomUUID(),
        explanation: 'Updated rationale',
      },
    }
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json(awaiting))
        .mockResolvedValue(json(next)),
    )
    const { user } = mount()
    await connect(user)
    await loaded()
    await user.click(screen.getByRole('button', { name: 'Review approval' }))
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved action' }),
    )
    await screen.findByText(
      'The proposal changed. Review the current version before deciding.',
    )
    expect(
      screen.queryByRole('button', { name: 'Approve version 1' }),
    ).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Review approval' }))
    expect(
      screen.getByRole('button', { name: 'Approve version 2' }),
    ).toBeTruthy()
  })

  it('requires a saved-state read after an uncertain decision and never assumes execution', async () => {
    let failed = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.method === 'POST') {
          failed = true
          throw new TypeError('private details')
        }
        return json(failed ? fixtures.unconfirmed : awaiting)
      }),
    )
    const { user } = mount()
    await connect(user)
    await loaded()
    await user.click(screen.getByRole('button', { name: 'Review approval' }))
    await user.click(screen.getByRole('button', { name: 'Approve version 1' }))
    await screen.findByText(/Your request may have been saved/)
    expect(
      screen.getByRole<HTMLButtonElement>('button', { name: 'Review approval' })
        .disabled,
    ).toBe(true)
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved action' }),
    )
    await screen.findByText(/Approved; execution is not confirmed/)
    expect(screen.queryByText(/Simulated ticket ID:/)).toBeNull()
  })

  it.each(['unknown', 'unconfirmed', 'rejected', 'success'])(
    'renders saved %s as a separate receipt and execution outcome',
    async (state) => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => json(fixtures[state])),
      )
      const { user } = mount()
      await connect(user)
      await loaded()
      expect(
        screen.queryByRole('button', { name: 'Review approval' }),
      ).toBeNull()
      expect(
        screen.queryByRole('button', {
          name: /retry execution|execute action/i,
        }),
      ).toBeNull()
      if (state === 'unknown')
        expect(screen.getByText(/The effect is unknown/)).toBeTruthy()
    },
  )

  it('preserves stale data during a transient read error, closes confirmation, and clears invalid results', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json(awaiting))
        .mockRejectedValueOnce(new TypeError('private'))
        .mockResolvedValue(
          json({
            ...awaiting,
            proposal: {
              ...p,
              arguments: {
                ...p.arguments,
                issue_report_id: crypto.randomUUID(),
              },
            },
          }),
        ),
    )
    const { user } = mount()
    await connect(user)
    await loaded()
    await user.click(screen.getByRole('button', { name: 'Review approval' }))
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved action' }),
    )
    await screen.findByText(
      'Showing the last saved action. It may be out of date.',
    )
    expect(
      screen.queryByRole('button', { name: 'Approve version 1' }),
    ).toBeNull()
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved action' }),
    )
    await screen.findByText(/invalid action response/)
    expect(screen.queryByText(p.arguments.description)).toBeNull()
  })

  it('closes confirmation on disconnect and requires refresh after reconnect', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(awaiting)),
    )
    const { user } = mount()
    await connect(user)
    await loaded()
    await user.click(screen.getByRole('button', { name: 'Review rejection' }))
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    await screen.findByText(/Disconnected/)
    expect(
      screen.queryByRole('button', { name: 'Reject version 1' }),
    ).toBeNull()
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    expect(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Review rejection',
      }).disabled,
    ).toBe(true)
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved action' }),
    )
    await waitFor(() =>
      expect(
        screen.getByRole<HTMLButtonElement>('button', {
          name: 'Review rejection',
        }).disabled,
      ).toBe(false),
    )
  })

  it.each([401, 403, 404])(
    'clears protected proposal after HTTP %s',
    async (status) => {
      const onLost = vi.fn()
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockResolvedValueOnce(json(awaiting))
          .mockResolvedValue(json({}, status)),
      )
      const { user } = mount(onLost)
      await connect(user)
      await loaded()
      await user.click(
        screen.getByRole('button', { name: 'Refresh saved action' }),
      )
      await screen.findByText(/unavailable to your support identity/)
      expect(screen.queryByText(p.arguments.description)).toBeNull()
      expect(onLost).toHaveBeenCalled()
    },
  )

  it('clears the combined support view when action access is revoked', async () => {
    let revoked = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.url.endsWith('/intake-run'))
          return json(timelineFixture.run)
        if (request.url.endsWith('/evidence-analysis'))
          return json(evidenceFixture)
        return revoked ? json({}, 403) : json(awaiting)
      }),
    )
    const { user } = mount(vi.fn(), true)
    await connect(user)
    await loaded()
    await screen.findByText('Intake started')
    revoked = true
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved action' }),
    )
    await screen.findByText(
      'Your access to this report is no longer available.',
    )
    expect(screen.queryByText(p.arguments.description)).toBeNull()
    expect(screen.queryByText('Intake started')).toBeNull()
    expect(document.querySelector('pre')).toBeNull()
  })

  it('isolates late mutation responses after changing report and session', async () => {
    let finish!: (value: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn((request: Request) =>
        request.method === 'POST'
          ? new Promise<Response>((resolve) => {
              finish = resolve
            })
          : Promise.resolve(
              json(
                new URL(request.url).pathname.includes(id)
                  ? awaiting
                  : {
                      ...fixtures.absent,
                      report_id: '33333333-3333-4333-8333-333333333333',
                    },
              ),
            ),
      ),
    )
    const { user, router } = mount()
    await connect(user)
    await loaded()
    await user.click(screen.getByRole('button', { name: 'Review approval' }))
    await user.click(screen.getByRole('button', { name: 'Approve version 1' }))
    await screen.findByText('Submitting decision…')
    await act(async () => {
      await router.navigate({
        to: '/support/reports/$reportId',
        params: { reportId: '33333333-3333-4333-8333-333333333333' },
      })
    })
    await screen.findByText('No action is currently proposed.')
    await act(async () => {
      finish(json(fixtures.success))
    })
    expect(screen.queryByText('Saved decision: Approved')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'End session' }))
    await connect(user, 'support-two')
    await screen.findByText('No action is currently proposed.')
    expect(screen.queryByText(p.arguments.description)).toBeNull()
  })
})

describe('proposal preparation', () => {
  it('replays an uncertain preparation with the same UUID and original fields', async () => {
    const bodies: unknown[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.method === 'GET') return json(fixtures.absent)
        const body = await request.json()
        bodies.push(body)
        if (bodies.length === 1) throw new TypeError('private connection error')
        return json({ ...awaiting, preparation_id: body.operation_id })
      }),
    )
    const { user } = mount()
    await connect(user)
    await user.type(
      await screen.findByLabelText('Ticket title'),
      p.arguments.title,
    )
    await user.type(
      screen.getByLabelText('Ticket description'),
      p.arguments.description,
    )
    await user.type(
      screen.getByLabelText('Why propose this action?'),
      p.explanation,
    )
    await user.click(
      screen.getByRole('button', { name: 'Save proposal for review' }),
    )
    await screen.findByText(/A preparation request has an uncertain outcome/)
    expect(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Retry accepted preparation',
      }).disabled,
    ).toBe(true)
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved action' }),
    )
    await user.click(
      screen.getByRole('button', { name: 'Retry accepted preparation' }),
    )
    await loaded()
    expect(bodies).toHaveLength(2)
    expect(bodies[0]).toEqual(bodies[1])
  })
  it('requires completed intake and does not offer creation on an archived report', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ ...fixtures.absent, can_prepare: false })),
    )
    const { user } = mount()
    await connect(user)
    await screen.findByText(
      'Customer intake must finish before support can prepare a proposal.',
    )
    expect(
      screen.queryByRole('button', { name: 'Save proposal for review' }),
    ).toBeNull()
  })

  it('saves manually authored fields with a server-bound report and nullable classification', async () => {
    let body: unknown
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.method === 'GET') return json(fixtures.absent)
        body = await request.json()
        return json(awaiting)
      }),
    )
    const { user } = mount()
    await connect(user)
    await user.type(
      await screen.findByLabelText('Ticket title'),
      'Investigate missing issue report',
    )
    await user.type(
      screen.getByLabelText('Ticket description'),
      'Customer cannot find a previously submitted report. The cause remains unverified.',
    )
    await user.type(
      screen.getByLabelText('Why propose this action?'),
      'Support should investigate the reported visibility problem.',
    )
    await user.click(
      screen.getByRole('button', { name: 'Save proposal for review' }),
    )
    await loaded()
    expect(body).toMatchObject({
      expected_fingerprint: null,
      service_code: null,
      severity: null,
    })
    expect(body).not.toHaveProperty('issue_report_id')
  })

  it('explicitly finishes interrupted preparation without presenting decision controls early', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) =>
        json(request.method === 'GET' ? fixtures.preparing : awaiting),
      ),
    )
    const { user } = mount()
    await connect(user)
    await screen.findByText(/Proposal preparation is unfinished/)
    expect(screen.queryByRole('button', { name: 'Review approval' })).toBeNull()
    await user.click(
      screen.getByRole('button', { name: 'Finish preparing proposal' }),
    )
    await waitFor(() =>
      expect(
        screen.getByRole<HTMLButtonElement>('button', {
          name: 'Review approval',
        }).disabled,
      ).toBe(false),
    )
  })
})

describe('action response validation', () => {
  it.each([
    { ...awaiting, status: 'simulated_success' },
    { ...awaiting, run_id: null },
    { ...awaiting, fingerprint: null },
    { ...awaiting, preparation_id: null },
    {
      ...fixtures.success,
      execution: {
        ...fixtures.success.execution!,
        fingerprint: 'a'.repeat(64),
      },
    },
    { ...fixtures.rejected, execution: fixtures.success.execution },
    { ...awaiting, timeline: [...awaiting.timeline, awaiting.timeline[0]] },
    { ...fixtures.absent, archived: true },
  ])('rejects inconsistent protected state', (value) =>
    expect(supportActionSchema.safeParse(value).success).toBe(false),
  )
})
