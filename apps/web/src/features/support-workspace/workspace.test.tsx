import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
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

import { WorkspaceSession } from '../session/workspace-session'
import { SupportReport } from '../execution-timeline/screens/support-report'
import timelineFixture from '../execution-timeline/timeline.fixture.json'
import evidenceFixture from '../evidence/evidence.fixture.json'
import actionFixture from '../approval/action.fixture.json'

// Mount every real section, query, runtime validator, and typed API client.
// Only HTTP is replaced; unexpected requests must fail the test.
const timeline = timelineFixture.run
const id = timeline.report_id
const metrics = {
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
    attempts: 1,
    usage: null,
    latency_ms: null,
    estimated_cost: null,
  },
}
const reads = {
  timeline: { path: 'intake-run', body: timeline, refresh: 'Refresh timeline' },
  evidence: {
    path: 'evidence-analysis',
    body: evidenceFixture,
    refresh: 'Refresh saved evidence',
  },
  action: {
    path: 'action',
    body: actionFixture.awaiting,
    refresh: 'Refresh saved action',
  },
  metrics: {
    path: 'execution-metrics',
    body: metrics,
    refresh: 'Refresh metrics',
  },
}
type Section = keyof typeof reads
const sections = Object.keys(reads) as Section[]
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function deferred() {
  let resolve!: (value: Response) => void
  const promise = new Promise<Response>((r) => {
    resolve = r
  })
  return { promise, resolve }
}
function mount(
  handler?: (
    request: Request,
    section?: Section,
  ) => Response | Promise<Response> | undefined,
) {
  const requests: Request[] = []
  vi.stubGlobal('scrollTo', vi.fn())
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      requests.push(request)
      const section = sections.find(
        (key) =>
          new URL(request.url).pathname ===
          `/support/issue-reports/${id}/${reads[key].path}`,
      )
      const overridden = handler?.(request, section)
      if (overridden !== undefined) return overridden
      if (request.method === 'GET' && section) return json(reads[section].body)
      throw new Error(
        `Unexpected request: ${request.method} ${new URL(request.url).pathname}`,
      )
    }),
  )
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
    component: () => <SupportReport reportId={page.useParams().reportId} />,
  })
  const router = createRouter({
    routeTree: root.addChildren([page]),
    history: createMemoryHistory({
      initialEntries: [`/support/reports/${id}`],
    }),
  })
  render(<RouterProvider router={router} />)
  return { user: userEvent.setup(), requests, router }
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
  await screen.findByText('Intake started')
  await screen.findByText(evidenceFixture.report.claims[0].draft.statement)
  await screen.findByText(actionFixture.awaiting.proposal.arguments.title)
  await screen.findByText('offline-intake-v1')
}
function expectProtectedDataHidden() {
  expect(screen.queryByText('Intake started')).toBeNull()
  expect(
    screen.queryByText(evidenceFixture.report.claims[0].draft.statement),
  ).toBeNull()
  expect(
    screen.queryByText(actionFixture.awaiting.proposal.arguments.title),
  ).toBeNull()
  expect(screen.queryByText('offline-intake-v1')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Review approval' })).toBeNull()
}
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('complete support workspace', () => {
  it('loads sections independently and never starts analysis or execution on open', async () => {
    const pending = Object.fromEntries(
      sections.map((key) => [key, deferred()]),
    ) as Record<Section, ReturnType<typeof deferred>>
    const { user, requests } = mount((_request, section) =>
      section ? pending[section].promise : undefined,
    )
    await connect(user)
    await screen.findByText('Loading saved action…')
    expect(screen.getByText('Loading saved evidence…')).toBeTruthy()
    expect(screen.getByText('Loading saved metrics…')).toBeTruthy()
    await act(async () => {
      pending.action.resolve(json(actionFixture.awaiting))
    })
    await screen.findByText(actionFixture.awaiting.proposal.arguments.title)
    expect(screen.getByText('Loading saved evidence…')).toBeTruthy()
    expect(screen.queryByText('Intake started')).toBeNull()
    await act(async () => {
      pending.metrics.resolve(json(metrics))
      pending.evidence.resolve(json(evidenceFixture))
      pending.timeline.resolve(json(timeline))
    })
    await loaded()
    expect(requests).toHaveLength(4)
    expect(
      requests.every(
        (r) =>
          r.method === 'GET' &&
          r.headers.get('Authorization') === 'Bearer support-one',
      ),
    ).toBe(true)
    expect(
      screen.getByRole('region', { name: 'Execution timeline' }),
    ).toBeTruthy()
    expect(
      screen.getByRole('region', { name: 'Approval timeline' }),
    ).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Evidence' })).toBeTruthy()
    expect(
      screen.getByRole('region', { name: 'Execution metrics' }),
    ).toBeTruthy()
  })

  it('keeps other saved sections readable when evidence fails, and retries only that read', async () => {
    let failed = true
    const { user, requests } = mount((_request, section) =>
      section === 'evidence' && failed
        ? json({ error: { message: 'private database detail' } }, 503)
        : undefined,
    )
    await connect(user)
    await screen.findByText('offline-intake-v1')
    await screen.findByText(actionFixture.awaiting.proposal.arguments.title)
    await screen.findByText('Intake started')
    const evidence = within(screen.getByRole('region', { name: 'Evidence' }))
    await evidence.findByRole('alert')
    expect(screen.queryByText('private database detail')).toBeNull()
    expect(
      evidence.queryByText(
        'No evidence analysis has been requested for this report.',
      ),
    ).toBeNull()
    const before = requests.length
    failed = false
    await user.click(
      evidence.getByRole('button', { name: 'Refresh saved evidence' }),
    )
    await evidence.findByText(evidenceFixture.report.claims[0].draft.statement)
    expect(
      requests.slice(before).map((r) => [r.method, new URL(r.url).pathname]),
    ).toEqual([['GET', `/support/issue-reports/${id}/evidence-analysis`]])
  })

  it.each(sections)(
    'clears every protected section when %s detects revoked access',
    async (source) => {
      let revoked = false
      const { user, requests } = mount((_request, section) =>
        revoked && section === source ? json({}, 403) : undefined,
      )
      await connect(user)
      await loaded()
      await user.click(screen.getByRole('button', { name: 'Review approval' }))
      expect(
        screen.getByRole('button', { name: 'Approve version 1' }),
      ).toBeTruthy()
      revoked = true
      await user.click(
        screen.getByRole('button', { name: reads[source].refresh }),
      )
      await screen.findByText(
        'Your access to this report is no longer available.',
      )
      expectProtectedDataHidden()
      expect(
        screen.queryByRole('button', { name: 'Approve version 1' }),
      ).toBeNull()
      expect(requests.every((r) => r.method === 'GET')).toBe(true)
    },
  )

  it.each(['timeline', 'evidence', 'metrics'] as const)(
    'does not restore an accepted decision arriving after %s revokes access',
    async (source) => {
      let revoked = false
      const decision = deferred()
      const { user, requests } = mount((request, section) => {
        if (request.method === 'POST' && request.url.endsWith('/decision'))
          return decision.promise
        if (revoked && section === source) return json({}, 403)
        return undefined
      })
      await connect(user)
      await loaded()
      await user.click(screen.getByRole('button', { name: 'Review approval' }))
      await user.click(
        screen.getByRole('button', { name: 'Approve version 1' }),
      )
      await screen.findByText('Submitting decision…')
      revoked = true
      await user.click(
        screen.getByRole('button', { name: reads[source].refresh }),
      )
      await screen.findByText(
        'Your access to this report is no longer available.',
      )
      await act(async () => {
        decision.resolve(json(actionFixture.success))
      })
      expectProtectedDataHidden()
      expect(screen.queryByText('Saved decision: Approved')).toBeNull()
      expect(requests.filter((r) => r.method === 'POST')).toHaveLength(1)
    },
  )

  it('does not restore evidence arriving after another section revokes access', async () => {
    let revoked = false
    const analysis = deferred()
    let operationId: string | undefined
    const { user, requests } = mount((request) => {
      if (
        request.method === 'POST' &&
        request.url.endsWith('/evidence-analyses')
      ) {
        void request
          .clone()
          .json()
          .then((body) => {
            operationId = body.operation_id
          })
        return analysis.promise
      }
      if (revoked && request.url.endsWith('/action')) return json({}, 403)
      return undefined
    })
    await connect(user)
    await loaded()
    await user.click(screen.getByRole('button', { name: 'Analyze evidence' }))
    await waitFor(() => expect(operationId).toBeDefined())
    revoked = true
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved action' }),
    )
    await screen.findByText(
      'Your access to this report is no longer available.',
    )
    await act(async () => {
      analysis.resolve(json({ ...evidenceFixture, operation_id: operationId }))
    })
    expectProtectedDataHidden()
    expect(requests.filter((r) => r.method === 'POST')).toHaveLength(1)
  })

  it('cancels all pending protected reads on session exit and ignores their late responses', async () => {
    const pending = Object.fromEntries(
      sections.map((key) => [key, deferred()]),
    ) as Record<Section, ReturnType<typeof deferred>>
    const { user, requests } = mount((_request, section) =>
      section ? pending[section].promise : undefined,
    )
    await connect(user)
    await screen.findByText('Loading saved metrics…')
    await waitFor(() => expect(requests).toHaveLength(4))
    await user.click(screen.getByRole('button', { name: 'End session' }))
    await waitFor(() =>
      expect(requests.every((r) => r.signal.aborted)).toBe(true),
    )
    await act(async () => {
      for (const section of sections)
        pending[section].resolve(json(reads[section].body))
    })
    expectProtectedDataHidden()
    expect(screen.getByLabelText('Demo support token')).toBeTruthy()
  })
})
