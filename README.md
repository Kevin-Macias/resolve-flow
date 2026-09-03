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

The web app uses
`VITE_API_URL=http://localhost:8000` by default; copy `apps/web/.env.example`
to `apps/web/.env` to override it.

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
