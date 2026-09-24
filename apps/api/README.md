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
Without this variable, those tests are skipped; for example:

```bash
TEST_DATABASE_URL=postgresql://resolve_flow:resolve_flow_local@localhost:5432/resolve_flow uv run pytest
```
