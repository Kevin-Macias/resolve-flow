# Workflow streaming contract (RF-503)

Status: Kevin approved the transport/lifecycle split, customer-only projection,
transport rules, and test expectations on 2026-10-09. RF-503's transport is
implemented, automatically verified, and accepted by Kevin when moving to the
next ticket. RF-503 is DONE within the approved transport scope.
RF-511 now supplies the durable run lifecycle and registered customer event
route; its implementation review is pending. See [customer intake runs](customer-intake-runs.md).

## Goal and current code

SSE lets an authorized browser observe saved progress and reconnect safely.
Separate HTTP operations handle customer answers and support decisions.

When RF-503 was implemented, the API exposed only customer report CRUD and
health/readiness endpoints; the graph had no run registry or HTTP lifecycle.
RF-511 now adds explicit customer start/read/clarification/recovery operations and
the SSE route. Creating a report through RF-502 still does not start analysis.

The [workspace design](workspace-information-architecture.md) tracks the other
customer and support integrations separately.

## Approved scope and sequencing

The application-owned SSE contracts, server streaming component, and browser
reader/reconnect controller use an injected, authorized snapshot source.
Deterministic adapters and HTTP tests exercise the transport without a live model
call or action execution. No production event route or streaming UI is registered
in this slice.

**RF-511: expose customer intake run lifecycle** is a separate PAIR
integration ticket before RF-504. It owns persisted run/report binding, run start,
current customer-safe status, explicit clarification resume, application lifetime,
and wiring the RF-503 transport into actual API routes. Its detailed execution,
concurrency, restart, and projection contract needs separate review. It must not
accept raw graph state, thread IDs, or `Command` objects from the browser.

RF-503 alone will not make the platform stream a real run. Completion must say
whether its source is a deterministic test adapter or the integrated lifecycle.
After RF-511, test actual endpoints and persistence before counting streaming as
ready for the platform checkpoint.

Internal support reads/projections, retrieval/diagnosis orchestration, and
proposal generation remain separately scoped dependencies. RF-512's report-state
lookup does not provide blanket access to internal workflow checkpoints.

## Transport and authorization

Use streaming `fetch` with `Authorization: Bearer ...`, an `Accept:
text/event-stream` header, and `AbortController`. Native browser `EventSource`
does not provide a custom bearer-header option. Do not put tokens in query
parameters or switch the authentication scheme just for SSE.

RF-511 registers the read-only GET for one run. Before opening the stream,
check identity, run/report binding, and current account access. A run ID grants
no permissions; execution requires separate authorized operations.

First integration exposes a customer-safe progress projection. It never streams
raw LangGraph updates, graph state, internal diagnosis/evidence, proposals,
approval records, model output, or the internal RF-310 event metadata. Support
streams need a separately reviewed authorization and projection contract.

Recheck current authorization before each snapshot read/send and on every
reconnection. A revoked identity or archived/inaccessible report closes the
stream without further protected data. Do not retain a request-scoped database
session or transaction for the lifetime of a connection.

## Event and snapshot contract

Stream complete current snapshots so reconnect restores state even after
missed notifications. Fetch persisted timeline history separately.

Each typed snapshot contains run ID, increasing positive revision, a defined
progress state, and any permitted customer update. Revision and progress describe
one committed view. RF-511 defines durable lifecycle revisions; browser timing
cannot supply them.

| SSE event | Contents | Client behavior |
| --- | --- | --- |
| `snapshot` | Versioned customer-safe snapshot with run-scoped revision ID | Replace the current snapshot after schema/run/revision validation |
| `stream_end` | Closed reason enum such as waiting for input, stage finished, or stage failed | Stop automatic reconnect; refresh/reopen after an explicit successful operation |
| `stream_error` | Closed sanitized reason such as unavailable or access lost | Follow retry/stop policy; never display raw exceptions |
| Heartbeat comment | No application data or event ID | Keep the connection alive without changing workflow state |

Use UTF-8 `text/event-stream` framing, JSON serialization for data, and a blank
line between frames. IDs are application-generated from a run and revision;
they cannot contain newline characters or source text. Heartbeats have no ID.
Use no-store response caching and disable proxy buffering where supported.

## Ordering, reconnect, and completion

1. On initial connection, send the latest authorized snapshot. Never invoke the
   graph to obtain it. Emit only committed changes in increasing revision order.
2. Resume requests send the last accepted ID in `Last-Event-ID`. Validate its
   format, run binding, and revision. Malformed, foreign-run, or future cursors
   fail before opening a successful stream.
3. Reconnect resends the latest complete snapshot, which may have the same ID
   as the last one seen. Equal revisions must contain identical data; the client
   ignores those duplicates. It accepts newer snapshots, rejects conflicting
   duplicates, and treats decreasing revisions as a protocol error.
4. Intermediate revisions may be coalesced. A revision gap is not missing audit
   history: refresh the current snapshot and use the timeline read for history.
   Do not invent an exactly-once notification guarantee.
5. Emit the final snapshot before `stream_end`. A clarification pause ends this
   connection without completing the whole business workflow. A finished intake
   stage awaiting customer confirmation is also not a created support ticket.
6. An interrupted network connection or unexpected EOF is not terminal workflow
   success. Show reconnecting/stale state and retry the read with bounded backoff.
   Delays are 1, 2, 4, 8, and 10 seconds, then show a manual reconnect
   action. Reset the budget only after a newer valid snapshot or 30 seconds of
   healthy streaming; duplicate snapshots alone do not reset it.
7. HTTP 401/403/404 and invalid cursor/protocol responses stop automatic retries.
   Retry network errors and transient server failures within the bounded budget.
   Before response headers, use the API error contract; after headers, send a
   sanitized control event when possible, then close.
8. Page navigation, session exit, or run change aborts the old fetch and pending
   retry timer. Late bytes from an old session cannot update the new session.
   Closing a reader never cancels, restarts, or resumes the underlying workflow.

By default, send a heartbeat every 15 seconds and roll over after one minute.
Rollover closes without `stream_end`, prompting cursor-based reconnect. Named,
tested configuration limits reads and frame buffers against stalls and malformed
streams; model/document content cannot set those limits.

## Approved acceptance tests

Kevin approved these behavior expectations before implementation. The automated
suite covers them with deterministic adapters; it does not establish production
authorization or persistence before RF-511.

- Frames round-trip through the browser parser even when UTF-8 characters, CRLF,
  JSON, and field boundaries are split across network chunks. Handle heartbeat
  comments and multiline data correctly; reject invalid payloads and oversized
  frames. An incomplete final frame is not applied.
- Increasing revisions apply in order, identical duplicates apply once, and
  conflicting duplicates/decreasing revisions stop with a protocol failure.
- Initial and reconnect reads return current snapshots; reconnect never invokes
  graph start/resume, performs a write, or dispatches a tool. No intermediate
  snapshot replay is required by this complete-snapshot contract.
- Unknown/foreign/future cursor, missing identity, wrong account, and access lost
  during a connection never expose protected snapshot data.
- Final snapshot precedes stream end; paused and finished stages stop retries.
  Abrupt EOF and temporary errors exercise bounded backoff without claiming
  completion. Non-retryable responses stop immediately.
- Aborting on navigation or identity change cancels reads/timers; old callbacks
  cannot update a new session. Heartbeat/lifetime rollover preserves the cursor.
- HTTP transport tests use an injected deterministic snapshot source and record
  authorization checks. They do not claim durable run execution or a working
  production lifecycle adapter before RF-511 is implemented.

## Implementation map

- `apps/api/src/api/streaming/transport.py`: immutable customer projection,
  cursor validation, authorization/read boundary, SSE framing, heartbeat, rollover,
  and sanitized stream errors. The source exposes only `authorize` and `read`;
  the transport imports no graph runner or tool. Each source operation has a
  five-second timeout and polling defaults to once per second.
- `apps/web/src/features/workflow-stream/parser.ts`: bounded incremental line and
  frame parsing. Comments do not dispatch events; incomplete frames at EOF are
  discarded. Frames are limited to 32,768 Unicode characters.
- `schemas.ts` in that directory: strict Zod snapshot/control payload schemas,
  safe-integer revisions, Unicode text bounds, and event ID validation.
- `contract.ts`: schema parsing, run/cursor binding, ordering, and duplicate
  comparison. Invalid payloads produce sanitized `ProtocolError` values.
- `client.ts` in that directory: bearer-header streaming fetch, cursor retention,
  retry budget, terminal/control events, and cancellation. A fetch/body read has a
  45-second inactivity timeout. `startCustomerStream` returns `stop` and `done`;
  consumers abort on navigation, identity change, and run change. Manual reopening
  may pass `initialSnapshot` for the same run. Consumers hide protected content
  when receiving `access_lost`; they never render raw error details.

The transport projection has `version: 1`, a UUID `run_id`, a positive revision
no greater than JavaScript's largest exact integer, `progress`, and nullable
`customer_update` (at most 2,000 Unicode characters). Progress is one of
`processing`, `waiting_input`, `stage_finished`, and `stage_failed`. These are
transport display states; RF-511 must define how committed lifecycle state maps
to them and allocate durable revisions. The authorized adapter must construct
customer-safe text rather than copy internal graph or model output.

Zod schemas validate stream payloads at runtime and are type-checked against
the generated `CustomerSnapshot` contract. Schemas preserve the lowercase UUID
format and count text bounds in Unicode code points. Update the runtime schemas
alongside API contract changes; generated TypeScript types alone do not validate
network data.
A shared SSE fixture is checked byte-for-byte by Python and parsed by browser
tests. RF-511's source reads a stored customer projection and revalidates
credentials, membership, and active report/run binding with short-lived sessions;
it does not retain the CRUD identity dependency's session for the stream.

## Verification and remaining review

`pnpm check` passed: formatting, lint, generated-client drift, strict Python and
TypeScript checks, production web build, 434 backend tests, and 47 frontend tests.
Forty existing database tests skipped without `TEST_DATABASE_URL`. RF-503 adds 24
backend tests and 36 frontend tests, including the shared Python/browser framing
fixture, bounded retry exhaustion, healthy-stream budget reset, truncated UTF-8
at EOF, access loss, source cancellation, and final snapshot/control ordering.
HTTP tests register an isolated test route and inject a deterministic source;
they do not exercise a real run registry or production identity/storage adapter.
No model calls, database migrations, or application writes were needed.

Kevin accepted the scoped implementation when requesting the next ticket.
RF-503 is DONE; UI platform review stays batched at the agreed checkpoint.
RF-511 is NEXT under the approved dependency order; its lifecycle, concurrency, restart, and authorization contract was approved
before implementation. Its implementation review is pending.
Kevin confirmed RF-511 first. Its approved detailed contract is in
[customer intake runs](customer-intake-runs.md); RF-504's remaining internal
timeline-read dependency is recorded in [the timeline UI scope](execution-timeline-ui.md).

References: [SSE standard](https://html.spec.whatwg.org/multipage/server-sent-events.html)
and [MDN's SSE guide](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events).


## RF-511 integration

`GET /intake-runs/{run_id}/events` reads the durable customer projection.
Pauses and intake completion end the connection. Internal timeline/state remain
private and execution uses separate operations. RF-511 tests use
real PostgreSQL run/checkpoint persistence and the actual HTTP route, including
cursor rejection and customer-safe terminal snapshots. The existing browser
controller remains independently tested; a customer streaming screen is later
UI work. See [the lifecycle mapping and setup](customer-intake-runs.md).
