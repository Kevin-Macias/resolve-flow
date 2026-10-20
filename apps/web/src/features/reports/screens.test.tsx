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

import type { IssueReport } from './api'
import { NewReport } from './screens/new-report'
import { ReportDetail } from './screens/report-detail'
import { ReportsList } from './screens/reports-list'
import { CustomerSession } from './session'

// CRUD behavior is tested independently; intake has its own integrated screen suite.
vi.mock('../customer-intake/components/intake-panel', () => ({
  IntakePanel: () => null,
}))

const id = '11111111-1111-4111-8111-111111111111'
const initial: IssueReport = {
  id,
  customer_account_id: '22222222-2222-4222-8222-222222222222',
  description: 'I submitted a report but cannot find it.',
  affected_service: null,
  status: 'submitted',
  submitted_by: {
    id: '33333333-3333-4333-8333-333333333333',
    name: 'Demo',
    last_name: 'Customer',
  },
  created_at: '2026-10-09T12:00:00Z',
  updated_at: '2026-10-09T12:00:00Z',
}
function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function mount(path = '/reports/') {
  vi.stubGlobal('scrollTo', vi.fn())
  const root = createRootRoute({
    component: () => (
      <CustomerSession>
        <Outlet />
      </CustomerSession>
    ),
  })
  const list = createRoute({
    getParentRoute: () => root,
    path: '/reports/',
    component: ReportsList,
  })
  const create = createRoute({
    getParentRoute: () => root,
    path: '/reports/new',
    component: NewReport,
  })
  const detail = createRoute({
    getParentRoute: () => root,
    path: '/reports/$reportId',
    component: () => <ReportDetail reportId={detail.useParams().reportId} />,
  })
  const router = createRouter({
    routeTree: root.addChildren([list, create, detail]),
    history: createMemoryHistory({ initialEntries: [path] }),
  })
  render(<RouterProvider router={router} />)
  return userEvent.setup()
}
async function connect(
  user: ReturnType<typeof userEvent.setup>,
  token = 'customer-one',
) {
  await user.type(await screen.findByLabelText('Demo customer token'), token)
  await user.click(screen.getByRole('button', { name: 'Open my reports' }))
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('customer report screens against the typed client', () => {
  it.each(['/reports/', `/reports/${id}`])(
    'rejects malformed successful responses without exposing their contents at %s',
    async (path) => {
      const invalid = {
        ...initial,
        affected_service: { code: 'reporting', label: 42 },
        description: 'private malformed response',
      }
      const fetchMock = vi
        .fn()
        .mockResolvedValue(json(path === '/reports/' ? [invalid] : invalid))
      vi.stubGlobal('fetch', fetchMock)
      const user = mount(path)
      await connect(user)
      expect((await screen.findByRole('alert')).textContent).toBe(
        'ResolveFlow returned an invalid report response. Refresh and try again.',
      )
      expect(screen.queryByText(invalid.description)).toBeNull()
      expect(fetchMock).toHaveBeenCalledTimes(1)
    },
  )

  it('creates, reads, updates, clears service, and archives only after confirmation', async () => {
    let saved = { ...initial }
    let exists = false
    const requests: Request[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        requests.push(request.clone())
        expect(request.headers.get('Authorization')).toBe('Bearer customer-one')
        if (request.method === 'POST') {
          const body = await request.json()
          expect(body).toEqual({
            description: initial.description,
            affected_service_code: null,
          })
          exists = true
          return json(saved, 201)
        }
        if (request.method === 'PATCH') {
          const body = await request.json()
          expect(Object.keys(body)).toEqual(['affected_service_code'])
          saved = {
            ...saved,
            affected_service: body.affected_service_code
              ? { code: body.affected_service_code, label: 'Reporting' }
              : null,
          }
          return json(saved)
        }
        if (request.method === 'DELETE') {
          exists = false
          return new Response(null, { status: 204 })
        }
        return json(
          new URL(request.url).pathname === '/issue-reports/'
            ? exists
              ? [saved]
              : []
            : saved,
        )
      }),
    )
    const user = mount()
    await connect(user)
    await screen.findByText('No reports yet')
    await user.click(screen.getByRole('link', { name: 'New report' }))
    await user.type(screen.getByLabelText('Description'), initial.description)
    await user.click(screen.getByRole('button', { name: 'Submit report' }))
    await screen.findByRole('heading', { name: 'Your report' })
    expect(screen.getByText(initial.description)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Edit service' }))
    await user.type(
      screen.getByLabelText('Affected service code (optional)'),
      'reporting',
    )
    await user.click(screen.getByRole('button', { name: 'Save service' }))
    await screen.findByText('Reporting (reporting)')
    await user.click(screen.getByRole('button', { name: 'Edit service' }))
    await user.clear(screen.getByLabelText('Affected service code (optional)'))
    await user.click(screen.getByRole('button', { name: 'Save service' }))
    await screen.findByText('No service specified')
    await user.click(screen.getByRole('button', { name: 'Archive report' }))
    expect(requests.filter((r) => r.method === 'DELETE')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Keep report' }))
    expect(requests.filter((r) => r.method === 'DELETE')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Archive report' }))
    await user.click(screen.getByRole('button', { name: 'Confirm archive' }))
    await screen.findByText('No reports yet')
    expect(requests.filter((r) => r.method === 'DELETE')).toHaveLength(1)
  })

  it('shows loading and an empty state, then refreshes the list', async () => {
    let finish: ((value: Response) => void) | undefined
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve
          }),
      )
      .mockResolvedValue(json([initial]))
    vi.stubGlobal('fetch', fetchMock)
    const user = mount()
    await connect(user)
    await screen.findByRole('status')
    expect(screen.getByText('Loading your reports…')).toBeTruthy()
    finish?.(json([]))
    await screen.findByText('No reports yet')
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    await screen.findByRole('link', { name: initial.description })
  })

  it('rejects whitespace locally and preserves the form after server validation failure', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        json({ error: { message: 'Unknown service code' } }, 422),
      )
    vi.stubGlobal('fetch', fetchMock)
    const user = mount('/reports/new')
    await connect(user)
    await user.type(screen.getByLabelText('Description'), '   ')
    await user.click(screen.getByRole('button', { name: 'Submit report' }))
    await screen.findByText(
      'Enter a description between 1 and 5,000 characters.',
    )
    expect(fetchMock).not.toHaveBeenCalled()
    await user.type(screen.getByLabelText('Description'), initial.description)
    await user.type(
      screen.getByLabelText('Affected service code (optional)'),
      'unknown',
    )
    await user.click(screen.getByRole('button', { name: 'Submit report' }))
    await screen.findByRole('alert')
    expect(
      (
        screen.getByLabelText('Description') as HTMLTextAreaElement
      ).value.trim(),
    ).toBe(initial.description)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it.each([401, 403, 404, 500])(
    'shows a safe unavailable state for HTTP %s',
    async (status) => {
      vi.stubGlobal(
        'fetch',
        vi
          .fn()
          .mockResolvedValue(
            json({ error: { message: 'private backend detail' } }, status),
          ),
      )
      const user = mount(`/reports/${id}`)
      await connect(user)
      await screen.findByRole('heading', { name: 'Report unavailable' })
      expect(screen.getByRole('alert').textContent).not.toContain(
        'private backend detail',
      )
      expect(screen.queryByText(initial.description)).toBeNull()
      if (status === 404)
        expect(screen.getByRole('alert').textContent).not.toContain('archived')
    },
  )

  it('does not retry uncertain archive effects and requires refresh before another attempt', async () => {
    let deletes = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.method === 'DELETE') {
          deletes++
          throw new TypeError('Failed to fetch')
        }
        return json(initial)
      }),
    )
    const user = mount(`/reports/${id}`)
    await connect(user)
    await screen.findByRole('heading', { name: 'Your report' })
    await user.click(screen.getByRole('button', { name: 'Archive report' }))
    await user.click(screen.getByRole('button', { name: 'Confirm archive' }))
    await screen.findByRole('alert')
    expect(deletes).toBe(1)
    expect(
      (
        screen.getByRole('button', {
          name: 'Confirm archive',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Keep report' }))
    expect(
      (
        screen.getByRole('button', {
          name: 'Archive report',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Refresh report' }))
    await screen.findByText('Report refreshed.')
    expect(
      (
        screen.getByRole('button', {
          name: 'Archive report',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false)
  })

  it('does not automatically retry a failed create and keeps the description', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValue(new TypeError('Connection lost'))
    vi.stubGlobal('fetch', fetchMock)
    const user = mount('/reports/new')
    await connect(user)
    await user.type(screen.getByLabelText('Description'), initial.description)
    await user.click(screen.getByRole('button', { name: 'Submit report' }))
    await screen.findByRole('alert')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(
      (screen.getByLabelText('Description') as HTMLTextAreaElement).value,
    ).toBe(initial.description)
    expect(screen.getByText(/the report may have been saved/)).toBeTruthy()
  })

  it('clears cached reports and form state when ending and changing the demo session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) =>
        json(
          request.headers.get('Authorization') === 'Bearer customer-one'
            ? [initial]
            : [],
        ),
      ),
    )
    const user = mount()
    await connect(user)
    await screen.findByRole('link', { name: initial.description })
    await user.click(screen.getByRole('button', { name: 'Log out' }))
    expect(screen.queryByText(initial.description)).toBeNull()
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
    await connect(user, 'customer-two')
    await screen.findByText('No reports yet')
    expect(screen.queryByText(initial.description)).toBeNull()
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  })

  it('ignores a previous session mutation result after switching identities', async () => {
    let finishCreate: ((value: Response) => void) | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.method === 'POST') {
          return new Promise<Response>((resolve) => {
            finishCreate = resolve
          })
        }
        return json([])
      }),
    )
    const user = mount('/reports/new')
    await connect(user)
    await user.type(screen.getByLabelText('Description'), initial.description)
    await user.click(screen.getByRole('button', { name: 'Submit report' }))
    await user.click(screen.getByRole('button', { name: 'Log out' }))
    await connect(user, 'customer-two')
    await act(async () => {
      finishCreate?.(json(initial, 201))
    })
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Your report' })).toBeNull(),
    )
    expect(screen.getByRole('heading', { name: 'What happened?' })).toBeTruthy()
    expect(
      (screen.getByLabelText('Description') as HTMLTextAreaElement).value,
    ).toBe('')
  })
})
