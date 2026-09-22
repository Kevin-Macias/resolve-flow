import os

import psycopg


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
            async with await psycopg.AsyncConnection.connect(
                db_url, connect_timeout=3
            ) as connection:
                await connection.execute("SELECT 1")
        except psycopg.Error as error:
            raise DatabaseUnavailableError() from error
