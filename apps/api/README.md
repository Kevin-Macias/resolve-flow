# Resolve Flow API

```bash
uv sync
uv run fastapi dev src/api/main.py
```

The health endpoint is available at `GET /health` and interactive OpenAPI docs
at `/docs`.

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
