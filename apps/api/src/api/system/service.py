import asyncio
import os

import psycopg
from alembic.util.exc import CommandError

from api.db.schema import checkpoint_version, expected_heads
from api.workflow.checkpoints import postgres_connection_url


class DatabaseNotConfiguredError(Exception):
    pass


class DatabaseUnavailableError(Exception):
    pass


class SystemService:
    async def check_database_readiness(self) -> None:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise DatabaseNotConfiguredError()
        try:
            heads = expected_heads()
            async with asyncio.timeout(5):
                async with await psycopg.AsyncConnection.connect(
                    postgres_connection_url(db_url), connect_timeout=3
                ) as connection:
                    await connection.execute("SET LOCAL statement_timeout = '3s'")
                    result = await connection.execute(
                        "SELECT version_num FROM public.alembic_version ORDER BY version_num"
                    )
                    actual = tuple(row[0] for row in await result.fetchall())
                    if actual != heads:
                        raise DatabaseUnavailableError()
                    result = await connection.execute(
                        "SELECT max(v) FROM workflow.checkpoint_migrations"
                    )
                    row = await result.fetchone()
                    if row is None or row[0] != checkpoint_version():
                        raise DatabaseUnavailableError()
        except (
            psycopg.Error,
            TimeoutError,
            ValueError,
            OSError,
            CommandError,
            RuntimeError,
        ) as error:
            raise DatabaseUnavailableError() from error
