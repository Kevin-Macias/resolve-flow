# Resolve Flow API

```bash
uv sync
uv run fastapi dev src/api/main.py
```

The health endpoint is available at `GET /health` and interactive OpenAPI docs
at `/docs`.

Customer issue-report routes support create (`POST /issue-reports/`), list,
read by ID, affected-service update (`PATCH /issue-reports/{id}`), and soft
archive (`DELETE /issue-reports/{id}`). PATCH accepts only
`affected_service_code`; status changes are internal-only. A `null` service code
clears the association, while omitting it leaves the association unchanged.
Archived reports are hidden from customer reads and cannot be changed again.

## LLM provider boundary

`api.extraction.provider` defines one async interface with an OpenAI adapter
and a deterministic fake. The OpenAI adapter uses the Responses API and needs
`OPENAI_API_KEY` only when constructed for a real call. No API endpoint invokes
it yet; ordinary tests use the fake or an injected SDK stub. The extraction
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
| 401 | `unauthorized` |
| 403 | `forbidden` |
| 404 | `not_found` |
| 409 | `conflict` |
| 422 | `validation_error` |
| 503 | `service_unavailable` |
| 500 | `internal_error` |

Other HTTP errors use `http_error`, except 405 (`method_not_allowed`).
Unexpected errors and HTTP errors with status 500 or above use generic public
messages. Unexpected errors log the exception type without its potentially
sensitive message. No current endpoint raises 409, but the contract is ready
for one.

## Database migrations

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
