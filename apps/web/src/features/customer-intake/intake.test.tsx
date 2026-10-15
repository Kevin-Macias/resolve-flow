import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
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
import { z } from 'zod'

import { ReportDetail } from '../reports/screens/report-detail'
import { CustomerSession } from '../reports/session'
import { customerRunSchema, type CustomerRun } from './schemas'
import rawFixtures from './intake.fixture.json?raw'

const fixtures = z
  .record(z.string(), customerRunSchema)
  .parse(JSON.parse(rawFixtures))
const id = fixtures.waiting.report_id
const report = {
  id,
  customer_account_id: '66666666-6666-4666-8666-666666666666',
  description: 'The profile save request failed.',
  affected_service: null,
  status: 'submitted',
  submitted_by: {
    id: '77777777-7777-4777-8777-777777777777',
    name: 'Demo',
    last_name: 'Customer',
  },
  created_at: '2026-10-12T12:00:00Z',
  updated_at: '2026-10-12T12:00:00Z',
}
function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function frame(run: CustomerRun) {
  return `id: ${run.run_id}:${run.revision}\nevent: snapshot\ndata: ${JSON.stringify(run.snapshot)}\n\n`
}
function ending(run: CustomerRun) {
  return `event: stream_end\ndata: ${JSON.stringify({ version: 1, reason: run.snapshot.progress })}\n\n`
}
function setup(initial: CustomerRun | null = fixtures.waiting) {
  let saved = initial
  const requests: Request[] = []
  let override:
    | ((
        request: Request,
      ) => Promise<Response | undefined> | Response | undefined)
    | undefined
  const controllers = new Set<ReadableStreamDefaultController<Uint8Array>>()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init)
      requests.push(request.clone())
      const response = await override?.(request)
      if (response) return response
      const path = new URL(request.url).pathname
      if (path.endsWith('/events')) {
        if (!saved) return json({}, 404)
        const current = saved
        if (current.snapshot.progress !== 'processing')
          return new Response(frame(current) + ending(current), {
            headers: { 'Content-Type': 'text/event-stream' },
          })
        return new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              controllers.add(controller)
              controller.enqueue(new TextEncoder().encode(frame(current)))
            },
            cancel() {
              controllers.clear()
            },
          }),
          { headers: { 'Content-Type': 'text/event-stream' } },
        )
      }
      if (path === `/issue-reports/${id}`) return json(report)
      if (request.method === 'GET') return saved ? json(saved) : json({}, 404)
      if (path.endsWith('/intake-run')) {
        saved = fixtures.waiting
        return json(saved, 201)
      }
      if (path.endsWith('/recover')) {
        saved = fixtures.waiting
        return json(saved)
      }
      const body = await request.json()
      saved =
        body.action === 'continue_incomplete'
          ? fixtures.incomplete
          : saved?.revision === 2
            ? fixtures.second
            : fixtures.complete
      return json(saved)
    }),
  )
  vi.stubGlobal('scrollTo', vi.fn())
  const root = createRootRoute({
    component: () => (
      <CustomerSession>
        <Outlet />
      </CustomerSession>
    ),
  })
  const detail = createRoute({
    getParentRoute: () => root,
    path: '/reports/$reportId',
    component: () => <ReportDetail reportId={detail.useParams().reportId} />,
  })
  const list = createRoute({
    getParentRoute: () => root,
    path: '/reports/',
    component: () => <h1>My reports</h1>,
  })
  const router = createRouter({
    routeTree: root.addChildren([detail, list]),
    history: createMemoryHistory({ initialEntries: [`/reports/${id}`] }),
  })
  render(<RouterProvider router={router} />)
  return {
    user: userEvent.setup(),
    requests,
    setSaved: (value: CustomerRun | null) => {
      saved = value
    },
    override: (value: typeof override) => {
      override = value
    },
    emit: (text: string) => {
      for (const controller of controllers)
        controller.enqueue(new TextEncoder().encode(text))
    },
  }
}
async function connect(
  user: ReturnType<typeof userEvent.setup>,
  token = 'customer-one',
) {
  await user.type(await screen.findByLabelText('Demo customer token'), token)
  await user.click(screen.getByRole('button', { name: 'Open my reports' }))
}
async function ready() {
  await waitFor(() =>
    expect(
      (
        screen.getByRole('button', {
          name: 'Refresh saved intake',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  )
}
function answer(question: string, value: string) {
  fireEvent.change(screen.getByLabelText(question), { target: { value } })
}
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('customer intake integration', () => {
  it('reads without starting, then explicitly starts once and shows scripted questions', async () => {
    const context = setup(null)
    await connect(context.user)
    await screen.findByRole('button', { name: 'Start intake' })
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(0)
    await context.user.click(
      screen.getByRole('button', { name: 'Start intake' }),
    )
    await screen.findByLabelText('What happened?')
    expect(screen.getByText(/Offline simulation/)).toBeTruthy()
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(1)
    expect(screen.queryByText('Execution timeline')).toBeNull()
  })

  it('validates all answers, binds ordered trimmed replies to the pause, and supports two saved rounds', async () => {
    const context = setup()
    await connect(context.user)
    await screen.findByLabelText('What happened?')
    await ready()
    await context.user.click(
      screen.getByRole('button', { name: 'Submit answers' }),
    )
    expect(screen.getByRole('alert').textContent).toContain(
      'Answer every question',
    )
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(0)
    answer('What happened?', '  Saving failed.  ')
    answer('What did you expect?', 'The profile should save.')
    await context.user.click(
      screen.getByRole('button', { name: 'Submit answers' }),
    )
    await screen.findByLabelText('When did this start?')
    await ready()
    const request = context.requests.find(
      (request) => request.method === 'POST',
    )!
    const body = await request.json()
    expect(body).toEqual({
      operation_id: expect.any(String),
      expected_revision: 2,
      pending_id: fixtures.waiting.pending!.pending_id,
      action: 'answer',
      answers: ['Saving failed.', 'The profile should save.'],
    })
    expect(body.operation_id).toMatch(/^[0-9a-f-]{36}$/)
    expect(screen.getByText('Previous answers')).toBeTruthy()
    expect(screen.getByText('Saving failed.')).toBeTruthy()
    answer('When did this start?', 'Today.')
    await context.user.click(
      screen.getByRole('button', { name: 'Submit answers' }),
    )
    await screen.findByText(/Intake is ready for summary confirmation/)
    expect(screen.getByText('Today.')).toBeTruthy()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Start intake' })).toBeNull()
  })

  it('uses Unicode character bounds and rejects oversized answers locally', async () => {
    const context = setup()
    await connect(context.user)
    await screen.findByLabelText('What happened?')
    await ready()
    answer('What happened?', '😀'.repeat(2001))
    answer('What did you expect?', 'Save.')
    await context.user.click(
      screen.getByRole('button', { name: 'Submit answers' }),
    )
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(0)
    answer('What happened?', '😀'.repeat(2000))
    await context.user.click(
      screen.getByRole('button', { name: 'Submit answers' }),
    )
    await screen.findByLabelText('When did this start?')
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(1)
  })

  it('confirms incomplete continuation, permits cancellation, and sends no unsaved answers', async () => {
    const context = setup()
    await connect(context.user)
    await screen.findByLabelText('What happened?')
    await ready()
    answer('What happened?', 'Unsent answer')
    await context.user.click(
      screen.getByRole('button', { name: 'Continue with incomplete context' }),
    )
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(0)
    await context.user.click(
      screen.getByRole('button', { name: 'Keep reviewing' }),
    )
    expect(
      (screen.getByLabelText('What happened?') as HTMLTextAreaElement).value,
    ).toBe('Unsent answer')
    await context.user.click(
      screen.getByRole('button', { name: 'Continue with incomplete context' }),
    )
    await context.user.click(
      screen.getByRole('button', { name: 'Confirm incomplete continuation' }),
    )
    await screen.findByText('Intake continued with incomplete context.')
    const body = await context.requests
      .find((request) => request.method === 'POST')!
      .json()
    expect(body.action).toBe('continue_incomplete')
    expect(body.answers).toEqual([])
  })

  it('shows continue-only at the round limit without inventing a third answer round', async () => {
    const context = setup(fixtures.limit)
    await connect(context.user)
    await screen.findByText(/The clarification limit has been reached/)
    await ready()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Submit answers' })).toBeNull()
    expect(
      screen.getByRole('button', { name: 'Continue with incomplete context' }),
    ).toBeTruthy()
  })

  it('preserves drafts across read refreshes and prevents duplicate pending submissions', async () => {
    const context = setup()
    await connect(context.user)
    await screen.findByLabelText('What happened?')
    await ready()
    answer('What happened?', 'Saving failed.')
    answer('What did you expect?', 'The profile should save.')
    await context.user.click(
      screen.getByRole('button', { name: 'Refresh saved intake' }),
    )
    await ready()
    expect(
      (screen.getByLabelText('What happened?') as HTMLTextAreaElement).value,
    ).toBe('Saving failed.')
    let finish!: (response: Response) => void
    context.override((request) =>
      request.method === 'POST'
        ? new Promise((resolve) => {
            finish = resolve
          })
        : undefined,
    )
    await context.user.dblClick(
      screen.getByRole('button', { name: 'Submit answers' }),
    )
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(1)
    expect(
      (screen.getByLabelText('What happened?') as HTMLTextAreaElement).disabled,
    ).toBe(true)
    context.setSaved(fixtures.second)
    await act(async () => {
      finish(json(fixtures.second))
    })
    await screen.findByLabelText('When did this start?')
  })

  it('does not retry an uncertain reply and reconciles accepted answers through a read', async () => {
    const context = setup()
    await connect(context.user)
    await screen.findByLabelText('What happened?')
    await ready()
    context.override((request) => {
      if (request.method === 'POST') {
        context.setSaved(fixtures.second)
        throw new TypeError('private connection detail')
      }
      return undefined
    })
    answer('What happened?', 'Saving failed.')
    answer('What did you expect?', 'The profile should save.')
    await context.user.click(
      screen.getByRole('button', { name: 'Submit answers' }),
    )
    await screen.findByRole('alert')
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(1)
    expect(
      (
        screen.getByRole('button', {
          name: 'Submit answers',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true)
    expect(screen.queryByText('private connection detail')).toBeNull()
    await context.user.click(
      screen.getByRole('button', { name: 'Refresh saved intake' }),
    )
    await screen.findByLabelText('When did this start?')
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(1)
  })

  it('requires a refresh after stale revision rejection and replaces obsolete questions', async () => {
    const context = setup()
    await connect(context.user)
    await screen.findByLabelText('What happened?')
    await ready()
    context.override((request) => {
      if (request.method === 'POST') {
        context.setSaved(fixtures.second)
        return json({}, 409)
      }
      return undefined
    })
    answer('What happened?', 'Old draft')
    answer('What did you expect?', 'Save.')
    await context.user.click(
      screen.getByRole('button', { name: 'Submit answers' }),
    )
    await screen.findByRole('alert')
    expect(
      (
        screen.getByRole('button', {
          name: 'Submit answers',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true)
    await context.user.click(
      screen.getByRole('button', { name: 'Refresh saved intake' }),
    )
    await screen.findByLabelText('When did this start?')
    expect(
      (screen.getByLabelText('When did this start?') as HTMLTextAreaElement)
        .value,
    ).toBe('')
    expect(screen.queryByLabelText('What happened?')).toBeNull()
  })

  it('offers explicit recovery only for an unfinished accepted operation', async () => {
    const context = setup(fixtures.recoverable)
    await connect(context.user)
    await screen.findByRole('button', { name: 'Recover saved operation' })
    await ready()
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(0)
    await context.user.click(
      screen.getByRole('button', { name: 'Recover saved operation' }),
    )
    await screen.findByLabelText('What happened?')
    const request = context.requests.find(
      (request) => request.method === 'POST',
    )!
    expect(new URL(request.url).pathname).toBe(
      `/intake-runs/${fixtures.recoverable.run_id}/recover`,
    )
    expect(await request.json()).toEqual({
      expected_revision: fixtures.recoverable.revision,
    })
  })

  it('does not offer recovery for a completed failure', async () => {
    const context = setup(fixtures.failed)
    await connect(context.user)
    await screen.findByText(/Intake failed/)
    expect(
      screen.queryByRole('button', { name: 'Recover saved operation' }),
    ).toBeNull()
    expect(screen.queryByRole('button', { name: 'Start intake' })).toBeNull()
  })

  it('fetches full questions when the stream ends at a new saved pause', async () => {
    const context = setup(fixtures.processing)
    await connect(context.user)
    await screen.findByText(/Processing intake/)
    context.setSaved(fixtures.waiting)
    await act(async () => {
      context.emit(frame(fixtures.waiting) + ending(fixtures.waiting))
    })
    await screen.findByLabelText('What happened?')
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(0)
  })

  it('hides the report and customer data when stream access is lost', async () => {
    const context = setup(fixtures.processing)
    await connect(context.user)
    await screen.findByText(/Processing intake/)
    await act(async () => {
      context.emit(
        'event: stream_error\ndata: {"version":1,"reason":"access_lost"}\n\n',
      )
    })
    await screen.findByRole('heading', { name: 'Report unavailable' })
    expect(screen.queryByText(report.description)).toBeNull()
    expect(screen.queryByText('Customer intake')).toBeNull()
  })

  it('ignores a reply result after ending and changing the session', async () => {
    const context = setup()
    await connect(context.user)
    await screen.findByLabelText('What happened?')
    await ready()
    let finish!: (response: Response) => void
    context.override((request) =>
      request.method === 'POST'
        ? new Promise((resolve) => {
            finish = resolve
          })
        : undefined,
    )
    answer('What happened?', 'Saving failed.')
    answer('What did you expect?', 'The profile should save.')
    await context.user.click(
      screen.getByRole('button', { name: 'Submit answers' }),
    )
    await context.user.click(
      screen.getByRole('button', { name: 'End session' }),
    )
    context.setSaved(null)
    await connect(context.user, 'customer-two')
    await screen.findByRole('button', { name: 'Start intake' })
    await act(async () => {
      finish(json(fixtures.second))
    })
    expect(screen.queryByText('Previous answers')).toBeNull()
    expect(screen.queryByLabelText('When did this start?')).toBeNull()
  })

  it('keeps clarification unavailable until the terminal stream update has a matching full read', async () => {
    const context = setup(fixtures.processing)
    await connect(context.user)
    await screen.findByText(/Processing intake/)
    let finish!: (response: Response) => void
    context.override((request) =>
      request.method === 'GET' &&
      new URL(request.url).pathname.endsWith('/intake-run')
        ? new Promise((resolve) => {
            finish = resolve
          })
        : undefined,
    )
    context.setSaved(fixtures.waiting)
    await act(async () => {
      context.emit(frame(fixtures.waiting) + ending(fixtures.waiting))
    })
    await waitFor(() => expect(finish).toBeDefined())
    expect(screen.queryByLabelText('What happened?')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Submit answers' })).toBeNull()
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(0)
    context.override(undefined)
    await act(async () => {
      finish(json(fixtures.waiting))
    })
    await screen.findByLabelText('What happened?')
    await ready()
    expect(
      (
        screen.getByRole('button', {
          name: 'Submit answers',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false)
  })

  it('preserves drafts but blocks replies during a transient saved-state read failure', async () => {
    const context = setup()
    await connect(context.user)
    await screen.findByLabelText('What happened?')
    await ready()
    answer('What happened?', 'My unsent draft')
    answer('What did you expect?', 'Save.')
    context.override((request) =>
      request.method === 'GET' &&
      new URL(request.url).pathname.endsWith('/intake-run')
        ? json({ error: { message: 'private infrastructure detail' } }, 503)
        : undefined,
    )
    await context.user.click(
      screen.getByRole('button', { name: 'Refresh saved intake' }),
    )
    await screen.findByText(/Showing the last saved intake/)
    expect(
      (screen.getByLabelText('What happened?') as HTMLTextAreaElement).value,
    ).toBe('My unsent draft')
    expect(
      (
        screen.getByRole('button', {
          name: 'Submit answers',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true)
    expect(screen.queryByText('private infrastructure detail')).toBeNull()
    context.override(undefined)
    await context.user.click(
      screen.getByRole('button', { name: 'Refresh saved intake' }),
    )
    await ready()
    expect(
      (
        screen.getByRole('button', {
          name: 'Submit answers',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false)
    expect(
      (screen.getByLabelText('What happened?') as HTMLTextAreaElement).value,
    ).toBe('My unsent draft')
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(0)
  })

  it('does not treat a previously visible run disappearing as permission to start another', async () => {
    const context = setup()
    await connect(context.user)
    await screen.findByLabelText('What happened?')
    await ready()
    context.override((request) =>
      request.method === 'GET' &&
      new URL(request.url).pathname.endsWith('/intake-run')
        ? json({}, 404)
        : undefined,
    )
    await context.user.click(
      screen.getByRole('button', { name: 'Refresh saved intake' }),
    )
    await screen.findByRole('heading', { name: 'Report unavailable' })
    expect(screen.queryByText(report.description)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Start intake' })).toBeNull()
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(0)
  })

  it('blocks clarification when streamed state cannot be verified', async () => {
    const context = setup()
    context.override((request) =>
      new URL(request.url).pathname.endsWith('/events')
        ? new Response(
            `id: ${fixtures.waiting.run_id}:${fixtures.waiting.revision}\nevent: snapshot\ndata: ${JSON.stringify({ ...fixtures.waiting.snapshot, revision: 'invalid' })}\n\n`,
            {
              headers: { 'Content-Type': 'text/event-stream' },
            },
          )
        : undefined,
    )
    await connect(context.user)
    await screen.findByText(/Update could not be verified/)
    expect(
      (
        screen.getByRole('button', {
          name: 'Submit answers',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true)
    expect(
      context.requests.filter((request) => request.method === 'POST'),
    ).toHaveLength(0)
  })

  it.each([
    { ...fixtures.waiting, report_id: report.customer_account_id },
    { ...fixtures.waiting, pending: null },
    { ...fixtures.waiting, simulated: false },
    {
      ...fixtures.waiting,
      snapshot: { ...fixtures.waiting.snapshot, revision: 1 },
    },
    { ...fixtures.waiting, internal_prompt: 'private prompt' },
  ])('rejects inconsistent full-run responses safely', async (invalid) => {
    const context = setup()
    context.override((request) =>
      new URL(request.url).pathname.endsWith('/intake-run')
        ? json(invalid)
        : undefined,
    )
    await connect(context.user)
    expect((await screen.findByRole('alert')).textContent).toContain(
      'invalid intake response',
    )
    expect(screen.queryByLabelText('What happened?')).toBeNull()
    expect(screen.queryByText('private prompt')).toBeNull()
  })
})
