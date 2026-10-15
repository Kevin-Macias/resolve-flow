# Customer intake run lifecycle (RF-511)

Status: DONE. Kevin approved the contract and implementation: durable registry,
customer operations, explicit recovery, and RF-503 route integration.
Verification results are below.

## Goal and boundaries

Customers can start intake for a visible report, read saved status and questions,
answer the current pause, and observe RF-503's progress stream. Explicit HTTP
operations drive the graph; refresh and reconnect are read-only.

Intake permits two answered rounds and explicit incomplete continuation, ending
at `needs_confirmation` or `extraction_failed`. Confirmation, support queue reads,
retrieval/diagnosis, proposals, approvals, and ticket creation are separate
integrations. Customer views exclude internal timeline events.

## Approved choices

1. Start intake explicitly after report creation. Database uniqueness enforces
   one run per report across workers. Repeated starts return that run unchanged,
   including after failure or completion.
2. Any currently authorized customer in the report's account can start, read,
   or answer its run while the report is active. Support users use separate
   endpoints.
3. POST requests await a pause, completion, or bounded failure. Execution stays
   in the request, without a job queue or durable background worker. GET/SSE read
   committed views. After disconnection, inspect saved state and explicitly
   recover interrupted work; the browser must not retry execution automatically.
4. Default to reviewed offline scripts with a saved simulation label. They
   demonstrate clarification and completion, without measuring model inference
   or relevance. Live mode requires explicit configuration and is excluded from
   implementation verification.

## HTTP contract

All routes require a bearer identity. UUIDs, strict closed request schemas, and
current account/report/run authorization are checked before protected reads or
execution. Client input never includes a thread ID, graph state, provider/model
choice, tool arguments, or raw LangGraph `Command`.

| Operation | Request | Result |
| --- | --- | --- |
| `POST /issue-reports/{report_id}/intake-run` | Empty JSON object `{}` | Create/start once; 201 for a new run, 200 for its existing run; return customer run view |
| `GET /issue-reports/{report_id}/intake-run` | None | Current customer run view; 404 when no accessible run exists |
| `GET /intake-runs/{run_id}` | None | Current customer run view |
| `POST /intake-runs/{run_id}/clarification` | Operation UUID, expected revision, pending pause UUID, action, ordered answers | Validate and advance only the current pause; return current customer run view |
| `POST /intake-runs/{run_id}/recover` | Expected revision | Explicitly recover an interrupted accepted operation; never start a second run or accept replacement answers |
| `GET /intake-runs/{run_id}/events` | Optional `Last-Event-ID` header | RF-503 customer snapshot stream; never execution |

Use the shared API error envelope: 401 for invalid/missing identity, 403 for an
unsupported role, 404 for absent/foreign/archived report or run, 409 for stale
revision/pause, conflicting operation reuse, or a busy mutation, 422 for malformed
input/cursor, and 503 for unavailable required infrastructure. Do not distinguish
foreign and nonexistent identifiers. Recheck access before returning protected
results, including cached duplicate-operation results.

Clarification accepts only `answer` or `continue_incomplete`. An answer contains
one trimmed nonempty string per current question, in saved order; at most two
answers and 2,000 Unicode characters per answer. Incomplete continuation has no
answers. The saved mode and two-round policy still apply. Validate before graph
invocation; invalid or stale HTTP input never causes a new interrupt, appends
answers, or calls a provider. Preserve the graph's existing internal reply
validation as a second check.

## Saved customer view and SSE

The versioned customer view contains run/report IDs, durable revision, intake
status, provider mode/simulation label, an application-authored message, current
clarification, and accepted question/answer turns. Extra fields are forbidden.
Expose the current pause ID, round, mode, cause, and selected customer questions;
keep internal clarification reasons and model/extraction records private.
Publish at most two current questions, each at most 2,000 Unicode characters.
Questions are customer-directed model output in live mode, not verified facts.
Render them as text. Validate bounds before publishing; an invalid projection
fails closed with a fixed safe failure message, never a truncated question that
changes the question/answer correspondence.

Never return the raw checkpoint, extraction object, preliminary diagnosis,
internal evidence, RF-310 metadata, approval bindings, or raw errors. Structured
summary confirmation needs its own later reviewed operation and projection.

The smaller RF-503 snapshot is part of the same stored view:

| Intake lifecycle | RF-503 progress | Stream end |
| --- | --- | --- |
| Accepted/executing operation | `processing` | No terminal end |
| Saved clarification pause | `waiting_input` | `waiting_input` after snapshot |
| Intake complete, needs confirmation | `stage_finished` | `stage_finished` after snapshot |
| Extraction/infrastructure failure requiring review | `stage_failed` | `stage_failed` after snapshot |

Save the customer view, SSE snapshot, and revision in one transaction. Revision
starts at 1, increases on view changes, survives restart, and stays within
RF-503's exact-integer limit. Accepting an operation clears obsolete input controls.
SSE publishes operation boundaries, not every graph node. GET/SSE read saved views.
After a crash, pending means unfinished, regardless of whether a worker is alive;
the recovery POST checks under the mutation lock.

Expose response schemas in OpenAPI and regenerate the client. Replace RF-503's
temporary handwritten payload type with generated response types while retaining
its runtime stream validation and shared framing fixture. RF-511 wires the server
source/route. RF-505 adds [customer clarification controls](customer-clarification-ui.md);
the broader workspace retains separate integration tickets.

## Persistence, concurrency, and recovery

Add an Alembic migration for a run registry and accepted-operation records.
The run binds an application-generated UUID to report/account IDs, initiating
user, fixed provider mode, revision, current public projection, and any pending
operation. Original report text stays in IssueReport; accepted customer answers
already belong in saved clarification state. If needed for recovery, accepted
operation payloads store those same bounded answers, never bearer tokens or raw
provider output, and are not logged or exposed as generic records.

Use a PostgreSQL advisory lock for each report's start, and for each run's
mutation/recovery. Use bounded/nonblocking acquisition with a safe busy response;
no concurrent graph advances for the same run. A concurrent start may receive
409 while creation is in progress; it can read the resulting run afterward. Keep ordinary SQLAlchemy read and
write transactions short; a dedicated lock connection may span execution but
must not hold a long report-row transaction during a model call. All mutation
paths use the same lock order, and shutdown/cancellation releases resources.

A clarification operation UUID binds to one canonical validated payload, including
its pause and expected revision. Persist acceptance before dispatch. Same UUID
and same payload returns the current authorized view without redispatch; same
UUID with different payload is 409. A different UUID against a consumed pause or
revision is 409. An unfinished accepted operation requires explicit recovery,
not a duplicate request that secretly advances it.

Registry/projection transactions and LangGraph checkpoint commits are separate;
do not claim cross-store atomicity. Use synchronous checkpoint durability and
reconcile only during an authorized, locked mutation/recovery:

- If no start checkpoint exists, initialize only the already accepted run.
- If checkpoint progress exists, continue from it rather than resubmitting the
  original input and starting its graph again.
- If the checkpoint is already at a final result or the operation's resulting
  pause, finalize the projection/operation without another provider call.
- For clarification, bind recovery to the originally accepted pause and payload.
  Inspect saved answer/continuation transition identities and checkpoint tasks to
  establish whether the reply was consumed. Never answer a newer pause with an
  older operation. If consistency cannot be established, fail closed for review.
- Recover only unfinished graph work. An unfinished model node may call the
  provider again; explicit recovery authorizes this possibility, not exactly-once
  provider billing. Committed answers and transition events must not duplicate.
  A completed extraction failure is not an interrupted operation and cannot be
  retried through recovery. General provider-failure retry remains separate work.

Crash tests must establish these cases against the installed LangGraph version,
including resume input written before an answer transition commits. Do not assume
that checking `pending_id` alone proves whether a reply has been consumed.

## Identity and resource lifetime

Use fresh short-lived sessions to check credentials, membership, active report,
and run/report/account binding on each source authorization/read/send. Recheck
through the trusted loader during extraction and clarification resume. Revocation
or archival stops future reads/operations, but cannot recall provider requests
already sent.

The application owns provider clients/configuration and database factories.
Each execution opens/closes a durable checkpointer. Missing configuration makes
intake unavailable, with no memory fallback; /health and CRUD stay available.
Migrations and recovery are explicit operations. Offline mode needs no API key.

## Approved acceptance tests

Kevin approved these expectations with the contract:

- Active account-scoped report starts once; simultaneous/repeated starts produce
  one persisted run. Completed runs never restart on start/read/reconnect.
- Missing/invalid credentials, support roles, foreign accounts, archived reports,
  and mismatched run/report bindings expose no protected state and invoke no
  provider. Token removal, membership changes, and archival after opening a
  stream stop further protected snapshots.
- Valid answers advance the current pause, preserve ordered turns, and enforce
  two rounds. Blank/oversized/partial answers, unknown fields, stale revision or
  pause, and invalid continuation never advance work.
- Same operation/payload reuses state, conflicting reuse fails, concurrent replies
  accept at most one, and unknown completion never causes blind redispatch.
- Process restart restores run binding, revisions, saved pause, and public view.
  Crash injection before dispatch, during resume consumption, after a committed
  answer, after a graph result, and before projection finalization exercises
  explicit recovery without duplicate accepted answers/events.
- GET/SSE performs no graph invocation, provider call, reconciliation, or write.
  The integrated RF-503 source emits stored snapshots and rejects invalid cursors;
  revisions and data remain consistent across reconnect and restart.
- Offline mode is labeled and deterministic; provider failures, cancellation,
  missing infrastructure, and projection errors remain sanitized and truthful.
- Migration round trip, generated client drift, strict types, lint, build, and
  relevant tests pass. Use disposable PostgreSQL for new persistence/concurrency
  checks. No live provider call is required.

## Implementation boundaries

1. Registry/operation schemas, migration, and account-scoped repository.
2. Locked intake service, provider wiring, projection publication, and recovery.
3. Authorized HTTP operations and RF-503 source/route with generated client types.
4. Database/process-restart, HTTP, and transport integration checks; document
   actual results and any environmental blocker before completion.

RF-504 also requires a separately reviewed support run/timeline read contract.
Customer lifecycle access grants no internal support permissions.

References: existing [clarification rules](workflow-clarification.md),
[checkpoint lifetime](workflow-checkpoints.md), and [streaming contract](workflow-streaming.md).
LangGraph's [interrupt documentation](https://docs.langchain.com/oss/python/langgraph/interrupts)
explains replay of the interrupted node; its
[persistence documentation](https://docs.langchain.com/oss/python/langgraph/persistence)
distinguishes durable checkpoints from in-memory storage. Application operation
identity, authorization, projection publication, and crash reconciliation above
are ResolveFlow responsibilities, not guarantees supplied by LangGraph.


## Setup and local API walkthrough

Apply the application migration and explicitly set up durable checkpoints before
using intake. Use your configured local database; these commands do not create
a customer identity or seed reports:

```bash
uv run --directory apps/api --env-file ../../.env alembic upgrade head
pnpm setup:checkpoints
```

Restart the API after changing environment configuration. Set
`INTAKE_PROVIDER_MODE=offline` (the default) for the local demonstration. Live mode
requires `INTAKE_PROVIDER_MODE=live`, `OPENAI_MODEL`, and `OPENAI_API_KEY`; a missing
or invalid provider configuration leaves intake unavailable while health and
customer CRUD remain available. Each existing run retains its mode; changing the
server mode does not switch a saved run to another provider mode during recovery.
Live provider quality and billing behavior have not been verified in this ticket.

Use `/docs` with a configured demo customer's bearer token:

1. Create a report through the existing issue-report endpoint.
2. POST `{}` to that report's `intake-run` endpoint. Offline mode returns one
   scripted clarification question; its summary, service, and severity are fixture
   values, not inferred customer facts.
3. GET the returned run and its events endpoint. Both only read saved state. Read
   the full run view first so the eventual UI can show its simulation label; the
   smaller SSE snapshot intentionally carries no internal metadata or provider
   configuration.
4. Submit a clarification with a fresh operation UUID, the returned revision and
   pending ID, `action: "answer"`, and one answer. Offline mode completes intake
   at `needs_confirmation`. Alternatively use `continue_incomplete` and no answers.
5. Repeat the exact same clarification request: it returns the current saved
   view without executing again. Changing the payload under the same operation
   UUID fails with 409. Use a fresh current view before any different operation.

The `/reports` screens provide CRUD and [clarification controls](customer-clarification-ui.md).
RF-511 supplies backend integration and types; RF-505 consumes them. Summary
confirmation remains planned. RF-513 supplies separate authorized support reads.

## Code map

- `intake/models.py` and migration `0003_customer_intake.py`: report-bound run,
  accepted payload, and public view storage; one run per report.
- `intake/schemas.py` and `projection.py`: bounded request/response contracts and
  explicit customer projections. Saved views include the matching SSE snapshot
  and durable revision.
- `intake/service.py`: fresh account checks, guarded operations, duplicate reuse,
  checkpoint reconciliation, and publication. `execute` only runs under the
  report lock; the recovery branch targets a saved interrupt ID and verifies the
  deterministic committed answer/continuation event before finalization.
- `intake/locks.py`: nonblocking PostgreSQL advisory lock shared by start and all
  mutations for a report. Ordinary read/write sessions close before model calls.
- `intake/runtime.py` and `provider.py`: durable graph contexts and the offline
  script. The application lifespan owns provider cleanup and database factories;
  no production operation uses an in-memory checkpoint fallback.
- `intake/router.py`: typed customer routes and shared safe infrastructure errors.
  `identity/dependencies.py` now shares identity resolution with the source so
  every stream check opens a fresh session and rechecks credentials/membership.
- `tests/intake`: real PostgreSQL lifecycle, concurrency, revocation, two-round,
  projection failure, cancellation, and recovery tests. A child interpreter checks
  restart restoration; a saved LangGraph resume-write fixture covers the gap
  before the interrupted answer node commits.

All paths above are relative to `apps/api/src/api`, except migration and test
paths under `apps/api`. The frontend SSE validator now uses generated
`CustomerSnapshot` types and keeps runtime validation of streamed bytes.

## Verification results

`pnpm check` passed formatting, lint, generated-client drift, strict Python and
TypeScript checks, the production web build, **504 backend tests**, and **47
frontend tests**. All database tests ran against a task-owned disposable
pgvector/PostgreSQL 17 database. RF-511 adds 30 intake tests; the existing migration
suite also runs migration 0003 through upgrade/downgrade, and the metadata test
now includes the new tables. Separate direct migration upgrade/downgrade/upgrade
checks passed. New schemas were isolated and cleaned up; the project database
and its volume were not migrated, seeded, or modified. No live provider call ran.

Full-suite verification required a clean disposable database: legacy knowledge
fixtures can discover public tables on their search path, and their migration
test requires no public Alembic version table. The intake fixtures explicitly
create their private tables even when public tables exist. A test helper import
was also corrected so collection of another suite's conftest cannot replace its
provider class at execution time. These setup corrections are included in the
passing full run.

Kevin approved the implementation. RF-511 is DONE; the integrated
platform walkthrough is still deferred to the agreed checkpoint. Live model
quality, frontend intake interaction, and internal support timeline authorization
are not established by these backend tests.
