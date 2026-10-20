# ResolveFlow architecture

Current implementation and target design are listed separately below.
Use the [roadmap](roadmap.md) for ticket status.
The [decision guide](architecture-decisions.md) records the learning goal behind
the stack and links the application choices that need context.

## Current implementation

The [Railway deployment runbook](railway-deployment.md) prepares the existing
Docker images for Kevin's selected Hobby hosting, with a private pgvector
database and separate web/API services. Services were provisioned on 2026-10-19;
Web/API HTTPS, schema readiness, anonymous denial, CORS, and deployed bundle
configuration checks pass. Authenticated browser verification and first-account
setup remain pending under RF-710.

[Continuous integration](continuous-integration.md) defines separate GitHub
Actions jobs for repository checks/fixture evaluations and container integration.
Tests use disposable PostgreSQL; evaluation steps keep their existing offline
contracts. Reports are retained as artifacts. The workflow uses read-only
repository permissions and no provider/deployment secrets.

[Container startup](container-startup.md) uses pinned build/runtime images and a
one-shot schema initializer. Compose waits for database health, successful
initialization, API schema readiness, then web health. Migrations run outside API
workers under a database advisory lock. Readiness verifies application/checkpoint
versions without repairing them. App containers run as non-root with read-only
roots and temporary storage; the existing local data volume is preserved.

[Request limits](request-limits.md) buffer bounded input before parsing and use
migration `0009` for shared PostgreSQL windows. Address checks run before route
handling; authenticated checks reserve user/account/model-operation allowance
before endpoint work. Counter failure stops dispatch. Health probes and CORS
preflight are exempt. The supported server ignores forwarded peer headers;
reverse-proxy deployments share the proxy address allowance until a trusted
client-address contract is configured.

The standalone [evaluation runner](evaluation-runner.md) executes approved fixture
scenarios through existing application boundaries. Approval uses temporary
PostgreSQL schemas and real in-process support HTTP handlers; clarification uses
in-memory graph checkpoints. JSON artifacts separate observations from labels
and leave their assessments unmeasured. The separate offline
[deterministic scorer](deterministic-metrics.md) compares those observations with
frozen labels, verifies citations and saved action bindings, and reports named
metrics with explicit denominators and errors. Semantic quality remains
unmeasured in deterministic reports. A separate
[rubric judge](rubric-judging.md) assesses approved extraction criteria with
versioned instructions and model provenance. Its default offline fixture leaves
semantic quality unmeasured; real judge calls require explicit opt-in and do not
change the fixture candidate mode. The offline
[report command](evaluation-report.md) binds these artifacts to matching
observations and produces Markdown with separate metrics, failures, provenance,
and compatible baseline comparisons. RF-607 adds a separately labeled
[prompt experiment](improvement-experiment.md) with an explicitly injected prompt,
bounded paired extraction calls, retained progress, and human semantic review.
The application prompt remains v3. These commands add no application endpoint.

Support [execution metrics](execution-metrics-ui.md) expose a read-only projection
of the latest saved intake extraction record through existing account grants.
The support page preserves configured model, prompt version, attempts, and returned
tokens in that limited snapshot. Separate [model accounting](model-accounting.md)
uses migration `0008` to persist each application provider attempt before
dispatch, retain usage/duration/outcomes independently of checkpoints,
and save versioned cost estimates. Intake and evidence scopes have separate
totals and explicit legacy coverage. Support loads the protected history on
request; hosting logs remain separate from this durable accounting store.
Standalone evaluation/ingestion commands are outside report accounting.


```text
Browser
  |
  | Customer CRUD/intake / support workspace / health requests
  v
TanStack Start + React + TypeScript        apps/web
  |
  v
FastAPI                                   apps/api
  |-- GET /health
  |-- GET /ready -- psycopg --> PostgreSQL
  |-- POST/GET/PATCH/DELETE /issue-reports -- SQLAlchemy --> PostgreSQL
  `-- Customer intake start/read/answer/recover + read-only SSE
        |-- Durable run registry/public projections -- SQLAlchemy --> PostgreSQL
        `-- Intake graph -- PostgreSQL checkpoints
```

[Invitation authentication](authentication-and-access.md) is the default identity
path. Migration `0007` adds password credentials, hashed expiring bearer sessions,
one-use invitations, support account grants, and login-attempt windows. A trusted
local CLI bootstraps a support administrator. Admin APIs issue invitations and
manage access; the recipient sets a password and later uses email/password login.
Administrator capability is separate from report-account grants. Session identity
snapshots reject role/account/admin changes, while support checks read current
grants. Browser tokens live in memory; logout revokes the server session.
Separate customer and support entry pages accept either account role. Password
sessions retain the validated role across navigation and redirect to that role's
workspace before rendering private screens. The boundary uses the displayed route
matches so pending navigation cannot expose the previous workspace with a new
session. Sign-out cancels queries, clears the cache, and invalidates late results.
Explicit `AUTH_MODE=demo` retains legacy environment maps without a password-mode
fallback. Offline evaluation fixtures select demo mode explicitly.

[Structured logging](structured-logging.md) emits metadata-only JSON to stdout
through the supported `api.server` entry point. Pure ASGI middleware creates a
request ID and observes response/stream completion. Context variables carry
request and authorized operation IDs through intake, provider attempts, approval,
and simulated execution. The same formatter sanitizes server/SDK records and
replaces raw access logging. Importing the app alone keeps CLI artifacts quiet.
Hosting owns collection, search, access, and retention; saved workflow events
and durable effect receipts remain the authoritative application history.

The monorepo currently provides:

- A pnpm workspace containing `apps/web`
- A Python project managed by uv in `apps/api`
- TanStack Start customer report CRUD and separate support timeline screens using
  a typed API client, Zod response validation, and TanStack Query
- A FastAPI service with liveness and database-readiness endpoints
- Async PostgreSQL connectivity through psycopg
- An app-scoped async SQLAlchemy engine and session factory, with a fresh
  session per database request and engine disposal at shutdown
- Declarative models and a reversible Alembic migration for customer accounts,
  users, services, and issue reports
- Customer-scoped issue-report create, list, read-by-ID, service update, and
  archive endpoints using current database identity and validated request bodies
- Shared API error responses with stable codes, safe messages, and validation
  field details
- A workspace API client generated from FastAPI OpenAPI output, with checked-in
  schema artifacts and a drift check
- A validated extraction output model for summary, tentative classification,
  reported facts, missing data, and questions
- An application-owned async LLM provider interface with OpenAI and deterministic
  fake adapters; the OpenAI adapter can request strict Structured Outputs
- Schema-validated extraction with typed refusal, empty/invalid output, and
  provider failures; bounded transient retries and in-memory prompt/model records.
  Endpoint wiring is described in the intake integration below
- A clarification policy that exposes missing or conflicting context and keeps
  at most two distinct model-proposed questions per extraction
- An opt-in live extraction check that reports schema shape, latency, and token
  usage without entering the normal test suite
- A minimal LangGraph workflow with typed classify, evaluate, preliminary
  diagnose, and report results; an injected trusted loader supplies report text,
  and typed extraction failures route directly to a safe report
- A bounded clarification branch with in-memory checkpoints: two rounds of
  questions, validated ordered answers, and explicit incomplete continuation
- An injectable async PostgreSQL checkpointer in a separate `workflow` schema,
  with explicit setup and typed-state restoration tested across process restarts
- Immutable typed `create_ticket` proposal contracts with revisions, risk,
  application-generated identities, and a fingerprint of the full snapshot;
  graph proposal generation is not implemented yet
- A separate reusable approval stage for saved proposals, with current support
  access checks, exact snapshot binding, typed decisions, and restart restoration
- An optionally injected simulated create-ticket tool after approval, with
  execution access rechecks and checkpointed deterministic fake results; no
  `SupportTicket` database row or external write is performed
- A guarded approval runner with per-run PostgreSQL advisory locks, first-decision
  preservation, duplicate outcome reuse, and checkpointed sanitized tool failures
- [Durable support simulation](tool-idempotency.md) with committed operation intent,
  separate atomic simulated effect/receipt storage, and an explicit recovery API.
  Real external effects still require a destination-specific idempotency contract
- Immutable Pydantic knowledge metadata and version-bound Markdown/PDF passage
  location contracts
- Manifest-driven CommonMark ingestion with exact text/line sections, SHA-256
  content and metadata hashes, and atomic in-memory revision storage
- PostgreSQL knowledge revision storage with an async transactional ingestion
  adapter, chunk and 1536-dimensional embedding tables, and exact cosine search
  support
- An application-owned async retrieval boundary with typed requests, ranked
  evidence, explicit access and active-revision scope, checked responses, and a
  deterministic offline fake
- Exact heading chunks, atomic repeatable indexing, a LangChain OpenAI embedding
  adapter, and PostgreSQL cosine search. Access/revision/status/profile filters
  run before ranking. Tests use deterministic vectors; live quality is unverified
- Supported/inference/gap/conflict claims with citations checked against source
  eligibility, hashes, exact sections, and versioned locations. Saved citations
  and text source labels are separate from the preliminary workflow diagnosis
- Evidence analysis with fixed versioned instructions and separate verified JSON
  source data. Output accepts only claim drafts with application-resolved citations.
  A separate support analysis service connects offline/live adapters and saved
  internal evidence responses; automatic workflow diagnosis, tool integration,
  and model-level injection testing remain separate work
- A retrieval evaluator with six reviewed cases, explicit hit/rank/coverage and
  failure measurements, fixture/live report modes, and a read-only baseline
  preflight; actual provider relevance remains unmeasured
- Typed execution timelines stored with graph transitions in checkpoint state,
  with ordered stage streams, stable event IDs, and closed sanitized metadata;
  a combined internal view preserves intake-before-approval order
- Database-backed endpoint tests isolated in rolled-back temporary schemas
- Factory-based tests for health and successful, misconfigured, and unavailable
  database-readiness behavior
- Dockerfiles and Docker Compose for web, API, and PostgreSQL
- Root development, test, build, and Docker commands

Customer PATCH can set or clear the affected service, but cannot change status.
DELETE archives the report by setting its status to `deleted`; archived reports
are excluded from customer reads and cannot be patched or archived again.
SQLAlchemy uses the database clock to refresh `updated_at` on ORM updates;
direct SQL writes do not currently have an update trigger. Internal status
transitions have not yet been implemented.

Customer report CRUD uses the generated client and TanStack Query with
session-scoped caches. Customer intake endpoints now invoke the existing graph
through authorized start, clarification, and explicit recovery operations.
The [customer intake lifecycle](customer-intake-runs.md) stores a report-bound run
and customer projection, serializes mutations with PostgreSQL advisory locks,
and uses durable checkpoints. Its default offline script is labeled simulation;
live provider mode is opt-in and unverified. Reads and the integrated RF-503 SSE
source return saved projections without graph execution or reconciliation.
Registry publication and checkpoint commits are separate; explicit recovery
reconciles interrupted accepted operations without duplicating committed answers.

The [minimal workflow](minimal-workflow.md) preserves reported facts and gaps;
cause stays unknown until evidence is available. Customer confirmation, automatic
retrieval/diagnosis orchestration, automatic proposals, and remaining support
workspace sections are unimplemented. RF-508 supplies a separately approved
manual support simulation over unconfirmed observations.
Customer report access rules are unchanged. Production requires durable
checkpoints; only the graph builder's test default uses memory.

The approved [workspace design](workspace-information-architecture.md) separates
customer and internal views. The [CRUD screens](customer-report-screens.md) are
available, with [customer clarification controls](customer-clarification-ui.md)
on report details. Full saved views provide questions and accepted answers;
SSE revisions prevent submitting an obsolete form, and commands use explicit
operation/revision/pause bindings. The
[internal timeline UI](execution-timeline-ui.md) at `/support` reads authorized
saved intake events. Customer and support routes use separate in-memory sessions;
access loss removes cached history, while temporary read failures show a stale
notice. Database-backed browser verification passed on 2026-10-12; the broader
platform walkthrough remains pending.
RF-511 customer endpoints do not expose RF-310's internal events or authorize
support checkpoint reads. RF-513 provides a separate
[support run read](support-run-reads.md):
`GET /support/issue-reports/{report_id}/intake-run` authorizes current support
users against explicit per-user account grants, including archived reports,
and returns validated saved intake events directly from PostgreSQL checkpoints.
This read-only endpoint works independently of model configuration and rechecks
access before return. Registry and checkpoint reads are separate snapshots.
Kevin accepted RF-513's final PAIR review on 2026-10-12. Approval-stage binding
remains separate work. RF-512 now provides an independent
[report-state lookup](support-report-state.md).
Inject the [PostgreSQL checkpointer](workflow-checkpoints.md) for durable storage;
the graph defaults to memory for offline tests.

The SQLAlchemy dependency opens/closes sessions; operations commit writes.
Closing an uncommitted session rolls back. Tests replace the dependency through
FastAPI's `dependency_overrides`. `/health` works without database configuration;
database operations require a configured factory.

RF-506 adds [preliminary support evidence analysis](evidence-panel.md) separately
from customer intake. Explicit POST operations reserve durable report-bound
records before retrieval/analysis and publish validated citation snapshots. GET
reads saved results with current report and source access checks. Operations use
the intake advisory lock to serialize accepted-answer changes and retain pending
state after interruption. Migration `0004` adds the analysis table; the app-scoped
service holds shared configuration, while PostgreSQL stores per-report state.
The support page uses generated types, Zod, and TanStack Query to display the
verified projection. The default is labeled fixture ranking and scripted analysis;
optional live adapters are configured separately and remain unverified against
live providers. Customer confirmation and automatic workflow diagnosis are unchanged.

RF-508's [support action integration](support-approval-controls.md) binds one
approval stage to an eligible intake run. Migration `0005` adds a report/run
registry and replayable proposal preparation records. Preparation and decision
operations take the report lock before the approval run lock; the guarded runner
checks the registered proposal against the checkpoint under that same run lock.
Current context is rechecked before a new decision and immediately before
simulated execution. Saved decisions allow read-only replay even if observations
later change. GET never advances or repairs a stage. An interrupted preparation
can be replayed explicitly. RF-703 now supplies a separate
[execution recovery command](tool-idempotency.md) for operations with durable
intent. Repeated decisions and GETs remain read-only. Migration `0006` adds the
operation ledger and simulated destination receipts. Recovery checks current
access, unchanged observations, and exact approval, then restores the saved
receipt or safely completes the same simulated operation. Unknown legacy
executions without an operation record remain manual. No real support ticket
or external integration is added.

## Target monorepo

```text
resolve-flow/
├── apps/
│   ├── api/                  # FastAPI, domain logic, workflow and tools
│   └── web/                  # TanStack Start, React and TypeScript
├── packages/
│   └── api-client/           # Generated client and TypeScript API types
├── knowledge/
│   ├── runbooks/             # Curated Markdown/PDF source material
│   └── sample-incidents/     # Retrieval and evaluation fixtures
├── docs/                     # Product, architecture and delivery records
└── docker-compose.yml
```

## Target runtime flow

```text
Customer request
  -> resolve current identity and access scope
  -> status lookup: retrieve own ticket or public incident -> safe response
  -> new report: extract and clarify -> customer confirms summary
  -> internal support queue
  -> retrieve authorized internal evidence
  -> generate diagnosis with evidence and uncertainty
  -> no action: final report
  -> action proposed: pause for human approval
       -> rejected: final report
       -> approved: validate and create ResolveFlow ticket -> safe customer status
```

The [workflow transitions](workflow-transitions.md) draw the new-report path,
including customer corrections, pauses, rejection, and explicit retries after
provider or retrieval failures. These are planned transitions, not implemented
graph behavior. The [clarification branch](workflow-clarification.md) implements
the reviewed RF-304 limits; evidence adequacy
rules belong to the retrieval tickets.

## Planned backend boundaries

- **HTTP layer:** validates transport data and maps errors to API responses.
- **Application services:** coordinate use cases without depending on HTTP.
- **Domain models:** define incidents, evidence, actions, approvals, and events.
- **Persistence:** owns SQLAlchemy models, repositories, and migrations.
- **LLM provider:** hides provider SDK details behind an application interface.
- **Retrieval:** returns ranked, typed evidence rather than raw model context.
- **Access policy:** filters records and fields before retrieval or model context
  construction; output policy produces a customer-safe projection.
- **Workflow:** uses LangGraph for durable branching, interruption, and resume.
- **Tools:** validate application-owned schemas and enforce authorization,
  approval, and idempotency before performing effects.
- **Evaluation:** executes a versioned dataset and stores measurable results.

## Planned core records

- `CustomerAccount` and `User`: tenant boundary and submitting identity; the
  user's role determines whether they act as a customer or internal operator
- `RequestContext`: application-established identity, role, and permissions
- `IssueReport`: immutable customer observation owned by one customer account
- `ReportTicketLink`: reviewed suspected, confirmed, or rejected match
- `SupportTicket`: team-owned internal work aggregating many issue reports
- `KnownIncident`: verified service event with an explicit public projection
- `WorkflowRun`: durable execution starting from an issue report, with an
  optional support-ticket link after approval and a terminal outcome
- `Clarification`: question, answer, and ordering metadata
- `Document` and `Chunk`: source metadata, content, and embeddings
- `Evidence`: retrieved chunk plus rank and relevance metadata
- `Diagnosis`: findings, cited claims, and uncertainty
- `ProposedAction`: tool, validated arguments, risk, and idempotency key
- `Approval`: decision tied to an immutable action version
- `ExecutionEvent`: append-only timeline record
- `ModelCall`: provider, model, prompt version, tokens, latency, and cost

## Safety invariants

1. Model output is untrusted until validated by an application-owned schema.
2. Retrieved content cannot redefine system instructions or tool policy.
3. Approval refers to an immutable hash or version of exact tool arguments.
4. A changed proposal invalidates previous approval.
5. Consequential tools require authorization and an idempotency key.
6. Logs and events exclude secrets and unnecessary sensitive content.
7. Clarification loops and retries have explicit limits.
8. Customer-visible responses use an explicit public projection; the model does
   not decide which internal fields are safe to reveal.
9. Ticket ownership, engineer assignment, action approval, and customer impact
   are separate relationships.

## Planned technology

| Area | Technology |
| --- | --- |
| API | Python, FastAPI, Pydantic |
| Persistence | PostgreSQL, SQLAlchemy, Alembic |
| Vector search | pgvector |
| LLM | OpenAI Responses API behind a provider interface |
| Orchestration | LangGraph |
| Retrieval integrations | Selected LangChain components where useful |
| Web | React, TypeScript, TanStack Start, TanStack Query, and Tailwind CSS |
| Streaming | Server-Sent Events |
| Tests and quality | pytest, Ruff, Pyright or mypy, frontend test tooling |

## Support report-state lookup

RF-512 exposes `GET /support/issue-reports/{report_id}/state` for current report
state, including archived reports. Kevin approved using the explicit support
account grants for this separate read. It requires no intake run or checkpoints
and rechecks access before returning a closed response. Customer reads continue
to exclude archived reports. Frontend integration remains separate; the endpoint
provides no archive actor/time history or restore operation. See the
[contract and verification](support-report-state.md).

## LangGraph typing boundary

`workflow/langgraph_types.py` types the builder and compiled graph methods in
use. Each builder is cast once; runtime objects and workflow policy stay unchanged.
`apps/api/typings/langgraph/graph/state.pyi` supplies the missing StateGraph
constructor typing through Pyright's default local `typings` directory.
Strict-mode diagnostics remain enabled.

The boundary checks node state, updates, and invocation inputs. Invocation/stream
values remain `Any` because they mix state and interrupt payloads; callers
validate or cast application state. Review the cast and stub when LangGraph
changes and verify compatibility through workflow tests. The interface covers
only the API subset in use.

PDF ingestion (RF-404) is deferred beyond the MVP. PDF location contracts remain
available for future work; the initial ingestion and retrieval slice uses Markdown.

The approved [chunking strategy](chunking-strategy.md) uses one substantive
Markdown section per chunk without overlap for the current corpus. Chunks retain
document metadata and exact source locations; title-and-metadata-only sections
do not become searchable passages. The [retrieval integration](retrieval-integration.md)
implements generation and persistence with a 512-token input budget. Longer
sections require a reviewed splitting
fallback and embedding input budget before ingestion for retrieval.
