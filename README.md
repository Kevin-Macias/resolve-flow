# Resolve Flow

Resolve Flow is a pnpm monorepo with a TanStack Start web application and a
FastAPI service.

It is being built as a portfolio project for an AI engineering role: a support
and incident copilot that turns an unstructured technical issue into a cited,
human-approved action plan. The project intentionally emphasizes durable LLM
workflows, evaluation, retrieval, and safe tool execution rather than a generic
chat interface.

## Project documentation

- [Product brief](docs/product.md): users, scope, workflow, and success criteria
- [Architecture](docs/architecture.md): current and target system design
- [Roadmap](docs/roadmap.md): phased tickets, ownership, and progress
- [Working agreement](docs/working-agreement.md): how Kevin and AI collaborate
- [Documentation index](docs/README.md): how these documents stay current

## Prerequisites

- Node.js 24.18.1 (the version pinned in `.nvmrc`)
- pnpm 10
- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
nvm install
nvm use
pnpm install
pnpm setup
```

Later sessions only need `nvm use` before running the Node.js commands. The
root `package.json` accepts compatible Node 24 releases but rejects other major
versions.

## Development

Run both applications from the repository root:

```bash
pnpm dev
```

- Web: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

Run formatting verification, linting, Python and TypeScript type checking,
backend tests, and informational branch coverage with:

```bash
pnpm check
```

The API client in `packages/api-client` uses types generated from FastAPI's
OpenAPI schema. After changing an API route or schema, run
`pnpm generate:api-client` and commit both generated files. `pnpm check` detects
client drift. The web app imports the typed client from the workspace package.

The web app uses
`VITE_API_URL=http://localhost:8000` by default; copy `apps/web/.env.example`
to `apps/web/.env` to override it.

Customer report screens are available at `/reports`. They use a demo customer
token entered in the browser, with account access enforced by the API. See
[customer report screens](docs/customer-report-screens.md) for identity setup,
supported edits, and the review walkthrough. `pnpm test:web` runs their offline
interaction tests and is included in `pnpm check`.

Customer intake start/read/clarification/recovery endpoints and a read-only SSE
route are also implemented. Apply migrations and checkpoint setup as documented
in [customer intake runs](docs/customer-intake-runs.md). They default to labeled
offline simulation. Report details now expose start, clarification, incomplete
continuation, and explicit recovery controls; see
[customer clarification UI](docs/customer-clarification-ui.md).

The support timeline is available at `/support`. Enter a configured support
token and a report ID to read its saved intake events. Support account grants
are enforced by the API, and switching between customer and support routes
requires a separate demo session. See [execution timeline UI](docs/execution-timeline-ui.md)
for setup, behavior, verification limits, and the database-backed walkthrough.

The support report page also offers **Analyze evidence** and **Refresh saved
evidence**. Apply migration `0004` first. Analysis defaults to labeled fixture
ranking and scripted output; opening or refreshing a page only reads saved
results. See the [evidence panel](docs/evidence-panel.md) for source verification,
access, optional live configuration, and interrupted-operation limits.

After intake finishes, support can draft a simulated ticket proposal, revise it
before a decision, and approve or reject its exact saved version. Apply migration
`0005` and checkpoint setup first. Approval receipts and execution outcomes remain
separate, and refreshing never retries execution. See
[support approval controls](docs/support-approval-controls.md) for the flow,
access rules, verification, and pending final PAIR review.

Support can also read a report's current state, including archival, through
`GET /support/issue-reports/{report_id}/state` within configured account grants.
It works without an intake run. See [support report state](docs/support-report-state.md)
for the response and access rules; this lookup is not yet connected to the UI.

## Docker

The Docker Compose project is named `resolve-flow` and runs PostgreSQL, the API,
and the web application:

```bash
cp .env.example .env
pnpm docker:up
```

Stop the stack with `pnpm docker:down`. Database data is retained in the
`resolve-flow-postgres-data` volume; use `docker compose down --volumes` only
when you intentionally want to delete local database data.

The API exposes two probes:

- `GET /health` checks that the process is alive.
- `GET /ready` verifies its PostgreSQL connection.

### Deployment

The application Dockerfiles are independent deployment targets:

- `apps/api/Dockerfile` for the FastAPI service
- `apps/web/Dockerfile` for the TanStack Start service

On Railway or a similar platform, provision managed PostgreSQL and pass its
`DATABASE_URL` to the API. Set `CORS_ORIGINS` to the public web URL. Build the
web image with `VITE_API_URL` set to the public API URL. Do not deploy the local
PostgreSQL service or reuse the development password in production.

Knowledge ingestion and pgvector setup are documented in
[vector storage](docs/vector-storage.md). Compose now selects a pgvector-enabled
PostgreSQL 17 image; existing Alpine database volumes need the documented
transition review before recreating their container.

Heading-aware indexing and the opt-in embedding command are documented in
[retrieval integration](docs/retrieval-integration.md). Search adapters are
implemented but are not connected to an endpoint or the workflow yet.
