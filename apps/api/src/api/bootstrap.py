"""Explicit one-shot database initialization; API workers never run migrations."""

import os
import subprocess
import sys

import psycopg

from api.db.schema import migration_config
from api.observability import emit
from api.observability.config import configure_logging
from api.workflow.checkpoints import postgres_connection_url

# Shared across application releases, and scoped by PostgreSQL to this database.
INITIALIZATION_LOCK = 0x52464C4F57


def initialize(database_url: str) -> None:
    child_environment = {**os.environ, "DATABASE_URL": database_url}
    with psycopg.connect(
        postgres_connection_url(database_url), autocommit=True, connect_timeout=5
    ) as guard:
        guard.execute("SET lock_timeout = '30s'")
        guard.execute("SELECT pg_advisory_lock(%s)", (INITIALIZATION_LOCK,))
        try:
            # Child processes have their own event loops and strict deadlines.
            # Suppress raw driver/SQL errors, which can contain credentials/data.
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "-c",
                    migration_config().config_file_name or "alembic.ini",
                    "upgrade",
                    "heads",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                env=child_environment,
            )
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import asyncio, os; from api.workflow.checkpoints import setup_checkpoints; asyncio.run(setup_checkpoints(os.environ['DATABASE_URL']))",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                env=child_environment,
            )
        finally:
            guard.execute("SELECT pg_advisory_unlock(%s)", (INITIALIZATION_LOCK,))


def main() -> None:
    configure_logging()
    emit("database.initialize.started")
    try:
        database_url = os.environ["DATABASE_URL"]
        initialize(database_url)
    except (Exception, KeyboardInterrupt):
        emit(
            "database.initialize.completed", outcome="error", failure_code="unavailable"
        )
        raise SystemExit(1) from None
    emit("database.initialize.completed", outcome="success")


if __name__ == "__main__":
    main()
