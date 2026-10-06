# ResolveFlow architecture

This document separates the repository's current implementation from its target
architecture. A component listed in the target design is not necessarily built.
The [roadmap](roadmap.md) is the progress source of truth.

## Current implementation

```text
Browser
  |
  | HTTP health request
  v
TanStack Start + React + TypeScript        apps/web
  |
  v
FastAPI                                   apps/api
  |-- GET /health
  |-- GET /ready -- psycopg --> PostgreSQL
  `-- POST/GET/PATCH/DELETE /issue-reports -- SQLAlchemy --> PostgreSQL
```

The monorepo currently provides:

- A pnpm workspace containing `apps/web`
- A Python project managed by uv in `apps/api`
- A TanStack Start placeholder interface that checks API health
- A FastAPI service with liveness and database-readiness endpoints
- Async PostgreSQL connectivity through psycopg
- An app-scoped async SQLAlchemy engine and session factory, with a fresh
  session per database request and engine disposal at shutdown
- Declarative models and a reversible Alembic migration for customer accounts,
  users, services, and issue reports
- Customer-scoped issue-report create, list, read-by-ID, service update, and
  archive endpoints using simulated identity and validated request bodies
- Shared API error responses with stable codes, safe messages, and validation
  field details
- A workspace API client generated from FastAPI OpenAPI output, with checked-in
  schema artifacts and a drift check
- A validated extraction output model for summary, tentative classification,
  reported facts, missing data, and questions
- An application-owned async LLM provider interface with OpenAI and deterministic
  fake adapters; the OpenAI adapter can request strict Structured Outputs
- An extraction service that requests the schema, validates returned JSON, and
  distinguishes refusal, empty output, malformed or invalid data, and provider
  failures; transient provider failures are retried within a fixed attempt and
  timeout budget, each outcome or error carries in-memory prompt and model
  settings metadata, and no endpoint invokes it yet
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
  preservation, duplicate outcome reuse, and checkpointed sanitized tool failures;
  real effect reconciliation and idempotency remain RF-703
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

The monorepo does not yet invoke extraction or the graph from an endpoint, or
provide retrieval or the incident
workspace UI. The [minimal workflow](minimal-workflow.md) records its scope:
diagnosis preserves reported facts and gaps with cause unknown until evidence
is available.
The [checkpoint integration](workflow-checkpoints.md) supports durable storage
when explicitly injected; the graph's default remains in-memory for offline tests.

The SQLAlchemy session dependency owns session lifetime, not transaction success:
application operations will explicitly commit writes. Closing an uncommitted
session rolls back its pending transaction. The dependency can be replaced with
FastAPI's `dependency_overrides` in tests. Missing database configuration leaves
`/health` available; database-backed operations require a configured factory.

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
  -> resolve simulated identity and access scope
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
| Web | React, TypeScript, TanStack Start and TanStack Query |
| Streaming | Server-Sent Events |
| Tests and quality | pytest, Ruff, Pyright or mypy, frontend test tooling |
