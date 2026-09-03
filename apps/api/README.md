# Resolve Flow API

```bash
uv sync
uv run fastapi dev src/api/main.py
```

The health endpoint is available at `GET /health` and interactive OpenAPI docs
at `/docs`.

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
