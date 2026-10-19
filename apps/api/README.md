# Resolve Flow API

```bash
uv sync
uv run python -m api.server --reload --host 127.0.0.1
```

The health endpoint is available at `GET /health` and interactive OpenAPI docs
at `/docs`.

Customer issue-report routes support create (`POST /issue-reports/`), list,
read by ID, affected-service update (`PATCH /issue-reports/{id}`), and soft
archive (`DELETE /issue-reports/{id}`). PATCH accepts only
`affected_service_code`; status changes are internal-only. A `null` service code
clears the association, while omitting it leaves the association unchanged.
Archived reports are hidden from customer reads and cannot be changed again.

## Operational logs

Use `python -m api.server` (or root `pnpm dev:api`) for metadata-only JSON logs
on stdout. Requests return `X-Request-ID`; run, model, and tool events carry
correlation IDs. Hosting controls collection, querying, and retention. See
[structured logging](../../docs/structured-logging.md) for fields, privacy rules,
server/SDK sanitization, and verification limits. Direct Uvicorn/FastAPI CLI
commands do not install this supported logging configuration.

## Authentication

Password authentication is the default. Apply migrations and bootstrap the first
admin from the repository root, with `DATABASE_URL` in the root `.env`:

```bash
uv run --directory apps/api --env-file ../../.env alembic upgrade head
uv run --directory apps/api --env-file ../../.env python scripts/manage_auth.py create-admin --email admin@example.com
```

The CLI prompts for a password. Use `/docs` to log in, authorize the bearer token,
and issue invitations. Recipients accept an invitation in the customer/support
web area, then use email/password on later visits. See
[authentication and access](../../docs/authentication-and-access.md) for the
admin endpoints, browser configuration, grants, and password recovery.
Existing demo fixtures require explicit `AUTH_MODE=demo` and matching web mode.

## Model accounting

Migration `0008` adds durable report-scoped model attempts. Apply migrations before
using intake or evidence generation. The API stops before live dispatch if an
accounting start cannot be saved. Optional `MODEL_PRICING` JSON supplies versioned
USD rates; missing rates produce unavailable estimates, never inferred zeros.
Support reads history through `/support/issue-reports/{id}/model-accounting`.
See [model accounting](../../docs/model-accounting.md) for setup, coverage,
interruption semantics, privacy, and the difference from provider billing.

## LLM provider boundary

`api.extraction.provider` defines one async interface with an OpenAI adapter
and a deterministic fake. The OpenAI adapter uses the Responses API and needs
`OPENAI_API_KEY` only when constructed for a real call. Customer intake and
preliminary evidence invoke it in explicit live mode; defaults remain offline.
Ordinary tests use the fake or an injected SDK stub. The extraction
service validates provider output, applies a bounded retry and clarification
policy, and returns prompt/model metadata. For the separate live model check,
add `OPENAI_API_KEY` and `OPENAI_MODEL` to the ignored root `.env` file and run
`pnpm test:live` from the root.

## API errors

Error responses use one JSON shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [{ "location": ["body", "description"], "code": "string_too_short" }]
  }
}
```

`code` is stable for client logic and localization. `message` is human-readable
and may change. `details` is always a list; request validation errors include
field locations and validation codes without submitted values. Other errors
currently use an empty list. The HTTP status remains authoritative.

| Status | Code |
| --- | --- |
| 400 | `bad_request` |
| 401 | `unauthorized` |
| 403 | `forbidden` |
| 404 | `not_found` |
| 409 | `conflict` |
| 422 | `validation_error` |
| 429 | `rate_limited` |
| 503 | `service_unavailable` |
| 500 | `internal_error` |

Other HTTP errors use `http_error`, except 405 (`method_not_allowed`).
Unexpected errors and HTTP errors with status 500 or above use generic public
messages. Unexpected errors log the exception type without its potentially
sensitive message. No current endpoint raises 409, but the contract is ready
for one.

## Database migrations

Workflow checkpoint tables have a separate explicit setup command,
`pnpm setup:checkpoints` from the repository root. See
[workflow checkpoints](../../docs/workflow-checkpoints.md) for the host-side
`DATABASE_URL`, schema ownership, connection lifetime, and restart behavior.

Start PostgreSQL and set `DATABASE_URL` to a local PostgreSQL connection string
(for example, `postgresql://resolve_flow:resolve_flow_local@localhost:5432/resolve_flow`).
Alembic selects the async psycopg driver automatically from that URL.

From this directory:

```bash
uv run alembic upgrade head
uv run alembic current
```

To inspect the initial migration's rollback on a disposable database, run
`uv run alembic downgrade base`. This removes the four application tables and
their data; do not run it against a database you need to keep. Migrations use
`DATABASE_URL` and do not run automatically when the API starts.

## Quality checks

Run individual backend checks from this directory:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
```

`pytest` reports statement and branch coverage without enforcing a minimum
percentage. From the repository root, `pnpm check` runs the backend checks and
the web type check together.

The issue-report HTTP/database tests run when `TEST_DATABASE_URL` is set to a
local PostgreSQL database URL. They create their own temporary schema inside a
transaction and roll it back after each test, leaving existing tables untouched.
The fixture verifies that its outer transaction rollback removed the schema.
Tests also check that a flushed report disappears after session rollback, a
session commit is visible to another session on the same test connection, and
archiving persists the `deleted` status during the test.
Without this variable, those tests are skipped; for example:

```bash
TEST_DATABASE_URL=postgresql://resolve_flow:resolve_flow_local@localhost:5432/resolve_flow uv run pytest
```

## Request limits

Apply migration `0009` before running the API. Shared PostgreSQL counters limit
requests, mutations, and model operations across workers. The API also caps
bodies at 64 KiB with a ten-second upload deadline. HTTP 429 includes
`Retry-After`; HTTP 413 identifies an oversized body. See
[request limits](../../docs/request-limits.md) for defaults, `REQUEST_LIMITS`,
proxy behavior, and failure rules.

## Container initialization and readiness

The API image includes migrations and the trusted admin CLI. Compose runs
`python -m api.bootstrap` once before API workers start; host development can
continue using explicit Alembic/checkpoint commands. `/ready` now requires both
schema versions to match this build. See [container startup](../../docs/container-startup.md)
for bounded initialization, health behavior, persistent volumes, and failure
handling. `pnpm docker:smoke` verifies an isolated full stack.
