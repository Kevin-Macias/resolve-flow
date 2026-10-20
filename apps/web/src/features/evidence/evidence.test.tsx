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

import { WorkspaceSession } from '../session/workspace-session'
import { SupportReport } from '../execution-timeline/screens/support-report'
import timelineFixture from '../execution-timeline/timeline.fixture.json'
import { EvidencePanel } from './evidence-panel'
import { supportEvidenceSchema } from './schemas'
import rawFixture from './evidence.fixture.json?raw'
vi.mock('../approval/action-panel', () => ({ ActionPanel: () => null }))

// Serialized by the actual Python evidence models and deterministic adapters.
const ready = supportEvidenceSchema.parse(JSON.parse(rawFixture))
const id = ready.report_id
const absent = {
  ...ready,
  status: 'absent',
  analysis_id: null,
  operation_id: null,
  created_at: null,
  provider_mode: null,
  simulated: false,
  passages: [],
  report: { claims: [] },
}
function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function mount(onAccessLost = vi.fn(), combined = false) {
  vi.stubGlobal('scrollTo', vi.fn())
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
    component: () =>
      combined ? (
        <SupportReport reportId={id} />
      ) : (
        <EvidencePanel reportId={id} onAccessLost={onAccessLost} />
      ),
  })
  const router = createRouter({
    routeTree: root.addChildren([page]),
    history: createMemoryHistory({
      initialEntries: [`/support/reports/${id}`],
    }),
  })
  render(<RouterProvider router={router} />)
  return userEvent.setup()
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

describe('support evidence panel', () => {
  it('removes both evidence and timeline when evidence access is revoked', async () => {
    let revoked = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.url.endsWith('/intake-run'))
          return json(timelineFixture.run)
        return revoked ? json({}, 404) : json(ready)
      }),
    )
    const user = mount(vi.fn(), true)
    await connect(user)
    await screen.findByText('Intake started')
    await screen.findByText(/fixture ranking and scripted analysis/)
    revoked = true
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved evidence' }),
    )
    await screen.findByText(/Your access to this report is no longer available/)
    expect(screen.queryByText('Intake started')).toBeNull()
    expect(document.querySelector('pre')).toBeNull()
  })
  it('loads saved evidence without starting analysis and shows provenance as plain text', async () => {
    const fetcher = vi.fn(async () => json(ready))
    vi.stubGlobal('fetch', fetcher)
    const user = mount()
    await connect(user)
    await screen.findByText(/fixture ranking and scripted analysis/)
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect((fetcher.mock.calls[0] as unknown as [Request])[0].method).toBe(
      'GET',
    )
    const passage = ready.passages[0]
    expect(
      screen.getAllByText(passage.citation.metadata.title).length,
    ).toBeGreaterThan(0)
    expect(screen.getAllByText(/Fixture score: 0.500/)).toHaveLength(5)
    const excerpts = document.querySelectorAll('pre')
    expect(excerpts[0].textContent).toBe(passage.citation.excerpt)
    expect(document.querySelector('a[href^="http"]')).toBeNull()
    expect(screen.getByText('Missing evidence')).toBeTruthy()
    expect(screen.getByText(/not confidence in a diagnosis/)).toBeTruthy()
  })

  it('distinguishes absent, pending, failed, empty search, and historical older input', async () => {
    const values = [
      absent,
      { ...ready, status: 'pending', passages: [], report: { claims: [] } },
      { ...ready, status: 'failed', passages: [], report: { claims: [] } },
      { ...ready, passages: [], report: { claims: [] } },
      {
        ...ready,
        older_input: true,
        passages: ready.passages.map((item) => ({ ...item, historical: true })),
      },
    ]
    const fetcher = vi.fn().mockImplementation(async () => json(values.shift()))
    vi.stubGlobal('fetch', fetcher)
    const user = mount()
    await connect(user)
    await screen.findByText(/No evidence analysis has been requested/)
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved evidence' }),
    )
    await screen.findByText(/pending or was interrupted/)
    expect(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Analyze evidence',
      }).disabled,
    ).toBe(true)
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved evidence' }),
    )
    await screen.findByText(/analysis failed/)
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved evidence' }),
    )
    await screen.findByText(/No eligible passages were returned/)
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved evidence' }),
    )
    await screen.findByText(/uses older observations/)
    expect(screen.getAllByText(/Historical source revision/)).toHaveLength(5)
  })

  it('prevents duplicate writes and binds the saved response to the operation UUID', async () => {
    let finish!: (value: Response) => void
    let operation!: string
    const fetcher = vi.fn(async (request: Request) => {
      if (request.method === 'GET') return json(absent)
      operation = (await request.json()).operation_id
      return new Promise<Response>((resolve) => {
        finish = resolve
      })
    })
    vi.stubGlobal('fetch', fetcher)
    const user = mount()
    await connect(user)
    await screen.findByText(/No evidence analysis/)
    await user.dblClick(
      screen.getByRole('button', { name: 'Analyze evidence' }),
    )
    await screen.findByRole('button', { name: 'Analyzing…' })
    expect(
      fetcher.mock.calls.filter(([request]) => request.method === 'POST'),
    ).toHaveLength(1)
    await act(async () => {
      finish(json({ ...ready, operation_id: operation }))
    })
    await screen.findByText(/fixture ranking and scripted analysis/)
  })

  it('requires refresh after an uncertain write and reuses its UUID when no outcome is visible', async () => {
    const operations: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.method === 'GET') return json(absent)
        const body = await request.json()
        operations.push(body.operation_id)
        throw new TypeError('private connection details')
      }),
    )
    const user = mount()
    await connect(user)
    await screen.findByText(/No evidence analysis/)
    await user.click(screen.getByRole('button', { name: 'Analyze evidence' }))
    await screen.findByText(/last analysis may have been accepted/)
    expect(
      screen.getByRole<HTMLButtonElement>('button', {
        name: 'Analyze evidence',
      }).disabled,
    ).toBe(true)
    expect(screen.queryByText('private connection details')).toBeNull()
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved evidence' }),
    )
    await user.click(screen.getByRole('button', { name: 'Analyze evidence' }))
    await screen.findByText(/last analysis may have been accepted/)
    expect(operations).toHaveLength(2)
    expect(operations[0]).toBe(operations[1])
  })

  it('retains stale evidence on transient failure and clears it on invalid data', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(json(ready))
        .mockRejectedValueOnce(new TypeError('private detail'))
        .mockResolvedValue(
          json({ ...ready, passages: [{ ...ready.passages[0], rank: 2 }] }),
        ),
    )
    const user = mount()
    await connect(user)
    await screen.findByText(/fixture ranking and scripted analysis/)
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved evidence' }),
    )
    await screen.findByText(/Showing stale saved evidence/)
    expect(document.querySelectorAll('pre')).toHaveLength(5)
    await user.click(
      screen.getByRole('button', { name: 'Refresh saved evidence' }),
    )
    await screen.findByText(/invalid evidence/)
    expect(document.querySelector('pre')).toBeNull()
  })

  it.each([401, 403, 404])(
    'clears protected evidence on HTTP %s and reports access loss',
    async (status) => {
      const onLost = vi.fn()
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockResolvedValueOnce(json(ready))
          .mockResolvedValue(json({}, status)),
      )
      const user = mount(onLost)
      await connect(user)
      await screen.findByText(/fixture ranking and scripted analysis/)
      await user.click(
        screen.getByRole('button', { name: 'Refresh saved evidence' }),
      )
      await screen.findByText(/unavailable to your support identity/)
      expect(document.querySelector('pre')).toBeNull()
      expect(onLost).toHaveBeenCalled()
    },
  )

  it('ignores a late mutation after ending and changing the session', async () => {
    let finish!: (value: Response) => void
    let operation!: string
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.method === 'POST') {
          operation = (await request.json()).operation_id
          return new Promise<Response>((resolve) => {
            finish = resolve
          })
        }
        return json(absent)
      }),
    )
    const user = mount()
    await connect(user)
    await screen.findByText(/No evidence analysis/)
    await user.click(screen.getByRole('button', { name: 'Analyze evidence' }))
    await screen.findByRole('button', { name: 'Analyzing…' })
    await user.click(screen.getByRole('button', { name: 'Log out' }))
    await connect(user, 'support-two')
    await screen.findByText(/No evidence analysis/)
    await act(async () => {
      finish(json({ ...ready, operation_id: operation }))
    })
    expect(document.querySelector('pre')).toBeNull()
    expect(window.localStorage.length).toBe(0)
  })

  it('shows claim relationships and renders source HTML as text', async () => {
    const citation = {
      ...ready.passages[0].citation,
      excerpt: '<script>steal()</script>',
    }
    const value = {
      ...ready,
      passages: [{ ...ready.passages[0], citation }],
      report: {
        claims: [
          {
            draft: {
              claim_id: 'review',
              kind: 'inference',
              statement: 'A possibility to review.',
              explanation: 'It does not establish the cause.',
              references: [{ chunk_id: citation.chunk_id, role: 'supports' }],
            },
            citations: [{ role: 'supports', citation }],
          },
        ],
      },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json(value)),
    )
    const user = mount()
    await connect(user)
    await screen.findByText('Inference')
    expect(
      within(screen.getByRole('region', { name: 'Evidence' })).getByText(
        /Supports:/,
      ),
    ).toBeTruthy()
    expect(screen.getByText('<script>steal()</script>')).toBeTruthy()
    expect(document.querySelector('script')).toBeNull()
  })
})

describe('evidence response validation', () => {
  it.each([
    { ...ready, simulated: false },
    { ...ready, analysis_id: null },
    { ...ready, status: 'pending' },
    { ...ready, passages: [...ready.passages, ready.passages[0]] },
    {
      ...ready,
      passages: [{ ...ready.passages[0], score_metric: 'cosine_similarity' }],
    },
    {
      ...ready,
      report: {
        claims: [
          {
            draft: {
              claim_id: 'bad',
              kind: 'supported',
              statement: 'Invented',
              references: [],
            },
            citations: [],
          },
        ],
      },
    },
  ])('rejects inconsistent saved results', (value) => {
    expect(supportEvidenceSchema.safeParse(value).success).toBe(false)
  })
})
