"""Fresh databases, schema-gated readiness, initialization, and sanitized failure."""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from psycopg import AsyncConnection, sql
from sqlalchemy.engine import make_url

from api.bootstrap import initialize
from api.db.schema import checkpoint_version, expected_heads
from api.main import create_app
from api.workflow.checkpoints import postgres_connection_url


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def database(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[str]:
    raw = os.getenv("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set TEST_DATABASE_URL for startup integration tests")
    base_url = postgres_connection_url(raw)
    name = f"rf_startup_{uuid4().hex}"
    async with await AsyncConnection.connect(base_url, autocommit=True) as connection:
        result = await connection.execute(
            "SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user"
        )
        row = await result.fetchone()
        if not row or not row[0]:
            pytest.skip(
                "Startup tests require a disposable PostgreSQL role with CREATEDB"
            )
        await connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
        )
    url = make_url(base_url).set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url)
    try:
        yield url
    finally:
        async with await AsyncConnection.connect(
            base_url, autocommit=True
        ) as connection:
            await connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


async def status() -> int:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/ready")
        if response.status_code != 200:
            assert response.json()["error"]["message"] == "Service unavailable"
        return response.status_code


@pytest.mark.anyio
async def test_fresh_database_then_concurrent_initializers_preserve_saved_data(
    database: str,
) -> None:
    assert await status() == 503
    await asyncio.to_thread(initialize, database)
    assert await status() == 200
    async with await AsyncConnection.connect(database, autocommit=True) as connection:
        await connection.execute(
            "INSERT INTO customer_accounts (name) VALUES ('Persistent smoke account')"
        )
    await asyncio.gather(
        asyncio.to_thread(initialize, database), asyncio.to_thread(initialize, database)
    )
    assert await status() == 200
    async with await AsyncConnection.connect(database) as connection:
        result = await connection.execute(
            "SELECT count(*) FROM customer_accounts WHERE name = 'Persistent smoke account'"
        )
        assert await result.fetchone() == (1,)
        result = await connection.execute(
            "SELECT version_num FROM alembic_version ORDER BY version_num"
        )
        assert tuple(row[0] for row in await result.fetchall()) == expected_heads()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "broken",
    ["application_old", "application_future", "checkpoint_missing", "checkpoint_old"],
)
async def test_readiness_rejects_schema_drift_without_repair(
    database: str, broken: str
) -> None:
    await asyncio.to_thread(initialize, database)
    revision = "0008" if broken == "application_old" else "future_revision"
    async with await AsyncConnection.connect(database, autocommit=True) as connection:
        if broken.startswith("application"):
            await connection.execute(
                "UPDATE alembic_version SET version_num = %s", (revision,)
            )
        elif broken == "checkpoint_missing":
            await connection.execute("DROP TABLE workflow.checkpoint_migrations")
        else:
            await connection.execute(
                "DELETE FROM workflow.checkpoint_migrations WHERE v = %s",
                (checkpoint_version(),),
            )
    assert await status() == 503
    async with await AsyncConnection.connect(database) as connection:
        if broken.startswith("application"):
            result = await connection.execute("SELECT version_num FROM alembic_version")
            assert await result.fetchone() == (revision,)
        elif broken == "checkpoint_missing":
            result = await connection.execute(
                "SELECT to_regclass('workflow.checkpoint_migrations')"
            )
            assert await result.fetchone() == (None,)
        else:
            result = await connection.execute(
                "SELECT max(v) FROM workflow.checkpoint_migrations"
            )
            assert await result.fetchone() == (checkpoint_version() - 1,)


@pytest.mark.anyio
async def test_failed_migration_exits_and_leaves_readiness_closed(
    database: str, tmp_path: Path
) -> None:
    root = tmp_path
    (root / "alembic.ini").write_text("[alembic]\nscript_location = missing\n")
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "api.bootstrap"],
        env={**os.environ, "RESOLVEFLOW_API_ROOT": str(root)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert events[-1]["event"] == "database.initialize.completed"
    assert events[-1]["outcome"] == "error" and result.stderr == ""
    assert await status() == 503


def test_initialization_failure_does_not_print_credentials_or_traceback() -> None:
    marker = "private-startup-secret"
    result = subprocess.run(
        [sys.executable, "-m", "api.bootstrap"],
        env={
            **os.environ,
            "DATABASE_URL": f"postgresql://{marker}:{marker}@127.0.0.1:1/{marker}",
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1 and marker not in result.stdout + result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout.splitlines()[-1])["outcome"] == "error"
