import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.system.service import DatabaseNotConfiguredError


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncGenerator[None]:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        app.state.session_factory = None
        yield
        return

    sqlalchemy_url = make_url(db_url).set(drivername="postgresql+psycopg")
    engine = create_async_engine(sqlalchemy_url)
    app.state.session_factory = async_sessionmaker[AsyncSession](
        engine, expire_on_commit=False
    )

    try:
        yield
    finally:
        app.state.session_factory = None
        await engine.dispose()


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] | None = (
        request.app.state.session_factory
    )
    if session_factory is None:
        raise DatabaseNotConfiguredError()

    async with session_factory() as session:
        yield session
