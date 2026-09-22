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
  `-- GET /ready -- psycopg --> PostgreSQL
```

The monorepo currently provides:

- A pnpm workspace containing `apps/web`
- A Python project managed by uv in `apps/api`
- A TanStack Start placeholder interface that checks API health
- A FastAPI service with liveness and database-readiness endpoints
- Async PostgreSQL connectivity through psycopg
- An app-scoped async SQLAlchemy engine and session factory, with a fresh
  session per database request and engine disposal at shutdown
- Factory-based tests for health and successful, misconfigured, and unavailable
  database-readiness behavior
- Dockerfiles and Docker Compose for web, API, and PostgreSQL
- Root development, test, build, and Docker commands

It does not yet provide incident persistence, an LLM integration, LangGraph,
retrieval, an API client package, or the incident workspace UI.

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
  -> classify and evaluate context
       -> insufficient: ask clarification -> resume retrieval
       -> sufficient: generate cited diagnosis
  -> no action: final report
  -> action proposed: pause for human approval
       -> rejected: final report
       -> approved: validate and create ResolveFlow ticket -> safe customer status
```

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
- `WorkflowRun`: durable execution state and terminal outcome
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
