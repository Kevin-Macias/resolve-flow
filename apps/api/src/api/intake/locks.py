import hashlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import HTTPException
from psycopg import AsyncConnection

from api.workflow.checkpoints import postgres_connection_url


class IntakeLocks:
    def __init__(self, database_url: str):
        self.url = postgres_connection_url(database_url)

    @asynccontextmanager
    async def hold(self, report_id: UUID) -> AsyncGenerator[None]:
        # One report key covers creation AND every run mutation: one lock order.
        digest = hashlib.sha256(f"resolveflow:intake:{report_id}".encode()).digest()
        async with await AsyncConnection.connect(
            self.url, autocommit=True, connect_timeout=5
        ) as connection:
            cursor = await connection.execute(
                "SELECT pg_try_advisory_lock(%s)",
                (int.from_bytes(digest[:8], "big", signed=True),),
            )
            row = await cursor.fetchone()
            if row is None or not row[0]:
                raise HTTPException(409, "Intake operation is busy")
            yield  # Session close releases the advisory lock, including cancellation.
