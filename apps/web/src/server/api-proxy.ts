import { createHash } from 'node:crypto'
import { apiSessionSchema, issuedSessionSchema } from '../features/session/session-contract'

const COOKIE = '__Host-resolveflow-session'
const LOCAL_COOKIE = 'resolveflow-session'
const MAX_BODY = 65_536
const allowed = /^\/(?:issue-reports|intake-runs|support\/issue-reports)(?:\/|$)/

function settings() {
  const webOrigin = new URL(process.env.WEB_ORIGIN ?? (process.env.NODE_ENV === 'production' ? '' : 'http://localhost:3000'))
  const apiOrigin = new URL(process.env.API_ORIGIN ?? (process.env.NODE_ENV === 'production' ? '' : 'http://localhost:8000'))
  for (const url of [webOrigin, apiOrigin]) {
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/' || url.search || url.hash)
      throw new Error('Invalid proxy origin')
    if (url.protocol !== 'https:' && !['localhost', '127.0.0.1', 'api', 'api.railway.internal'].includes(url.hostname))
      throw new Error('HTTPS required outside local/private networking')
  }
  if (webOrigin.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(webOrigin.hostname))
    throw new Error('Public web origin requires HTTPS')
  return { webOrigin: webOrigin.origin, apiOrigin: apiOrigin.origin, secure: webOrigin.protocol === 'https:' }
}
function cookieHeader(token: string, secure: boolean, expires?: string) {
  const attributes = `${secure ? COOKIE : LOCAL_COOKIE}=${token}; Path=/; HttpOnly; SameSite=Lax${secure ? '; Secure' : ''}`
  return expires ? `${attributes}; Expires=${new Date(expires).toUTCString()}` : `${attributes}; Max-Age=0`
}
function tokenFrom(request: Request, secure: boolean) {
  const values = (request.headers.get('cookie') ?? '').split(';').map((part) => part.trim())
    .filter((part) => part.startsWith(`${secure ? COOKIE : LOCAL_COOKIE}=`))
  const value = values.length === 1 ? values[0].slice(values[0].indexOf('=') + 1) : ''
  return /^rfs_[A-Za-z0-9_-]{43}$/.test(value) ? value : ''
}
function sessionId(token: string) { return createHash('sha256').update(token).digest('hex') }
function failure(status: number, message: string) {
  return Response.json({ detail: message }, { status, headers: { 'Cache-Control': 'no-store' } })
}
async function readBody(request: Request) {
  if (!request.body) return undefined
  const reader = request.body.getReader()
  const chunks: Uint8Array[] = []
  let length = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      length += value.byteLength
      if (length > MAX_BODY) { await reader.cancel(); return null }
      chunks.push(value)
    }
  } finally { reader.releaseLock() }
  const body = new Uint8Array(length)
  let offset = 0
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.length }
  return body
}

function forwardBody(body: ReadableStream<Uint8Array> | null, signal: AbortSignal) {
  if (!body) return null
  const reader = body.getReader()
  let cancelled = false
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const { done, value } = await reader.read()
        if (cancelled) return
        if (done) { controller.close(); reader.releaseLock() }
        else controller.enqueue(value)
      } catch {
        if (cancelled) return
        if (signal.aborted) controller.close()
        else controller.error(new Error('API response stream interrupted.'))
      }
    },
    async cancel() {
      cancelled = true
      await reader.cancel().catch(() => undefined)
    },
  })
}

/** Fixed API upstream; cookies and browser-supplied authorization never pass through. */
export async function proxyApi(request: Request): Promise<Response> {
  let config: ReturnType<typeof settings>
  try { config = settings() } catch { return failure(503, 'Session service is not configured.') }
  const incoming = new URL(request.url)
  const path = incoming.pathname.slice('/api'.length)
  const method = request.method
  const login = path === '/auth/login' || path === '/auth/invitations/redeem'
  const logout = path === '/auth/logout'
  const restore = path === '/auth/session'
  if (!incoming.pathname.startsWith('/api/') || /[%\\]/.test(path) || (!login && !logout && !restore && !allowed.test(path)))
    return failure(404, 'Endpoint unavailable.')
  if ((login || logout) && method !== 'POST' || restore && method !== 'GET' || !['GET', 'POST', 'PATCH', 'PUT', 'DELETE'].includes(method))
    return failure(405, 'Method unavailable.')
  const origin = request.headers.get('origin')
  const fetchSite = request.headers.get('sec-fetch-site')
  if ((origin && origin !== config.webOrigin) || (fetchSite && !['same-origin', 'none'].includes(fetchSite)))
    return failure(403, 'Request origin was not accepted.')
  if (method !== 'GET' && (origin !== config.webOrigin || request.headers.get('X-ResolveFlow-Request') !== '1'))
    return failure(403, 'Request origin was not accepted.')
  const token = tokenFrom(request, config.secure)
  if (!login && !token) {
    const response = logout ? new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } }) : failure(401, 'Sign in required.')
    response.headers.set('Set-Cookie', cookieHeader('', config.secure))
    return response
  }
  if (!login && !restore && request.headers.get('X-ResolveFlow-Session') !== sessionId(token))
    return failure(401, 'This browser session changed. Reload to continue.')
  const headers = new Headers({ Accept: request.headers.get('accept') ?? 'application/json' })
  if (!login) headers.set('Authorization', `Bearer ${token}`)
  for (const name of ['content-type', 'last-event-id', 'x-request-id']) {
    const value = request.headers.get(name)
    if (value) headers.set(name, value)
  }
  try {
    const body = method === 'GET' ? undefined : await readBody(request)
    if (body === null) return failure(413, 'Request body too large.')
    const upstream = await fetch(`${config.apiOrigin}${path}${incoming.search}`, {
      method, headers, body, redirect: 'manual', signal: request.signal,
    })
    // Redirects must not send credentials to another destination or expose login tokens.
    if (upstream.status >= 300 && upstream.status < 400) {
      await upstream.body?.cancel()
      return failure(502, 'Unexpected API redirect.')
    }
    const responseHeaders = new Headers({ 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' })
    for (const name of ['content-type', 'retry-after', 'x-request-id']) {
      const value = upstream.headers.get(name)
      if (value) responseHeaders.set(name, value)
    }
    if (login && upstream.ok) {
      const parsed = issuedSessionSchema.safeParse(await upstream.json())
      if (!parsed.success || Date.parse(parsed.data.expires_at) <= Date.now())
        return failure(502, 'Invalid session response.')
      responseHeaders.set('Set-Cookie', cookieHeader(parsed.data.access_token, config.secure, parsed.data.expires_at))
      return Response.json({ session_id: sessionId(parsed.data.access_token), expires_at: parsed.data.expires_at, user: parsed.data.user }, { status: upstream.status, headers: responseHeaders })
    }
    if (restore && upstream.ok) {
      const saved = apiSessionSchema.safeParse(await upstream.json())
      if (!saved.success || Date.parse(saved.data.expires_at) <= Date.now()) return failure(502, 'Invalid session response.')
      return Response.json({ ...saved.data, session_id: sessionId(token) }, { headers: responseHeaders })
    }
    if (logout || (!login && upstream.status === 401))
      responseHeaders.set('Set-Cookie', cookieHeader('', config.secure))
    if (responseHeaders.get('content-type')?.startsWith('text/event-stream'))
      responseHeaders.set('X-Accel-Buffering', 'no')
    return new Response(forwardBody(upstream.body, request.signal), { status: upstream.status, headers: responseHeaders })
  } catch {
    const response = failure(502, 'Could not reach ResolveFlow. Check saved state before repeating a change.')
    if (logout) response.headers.set('Set-Cookie', cookieHeader('', config.secure))
    return response
  }
}
