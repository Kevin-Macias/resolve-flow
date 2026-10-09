"""Disposable committed schemas for knowledge PostgreSQL checks."""

import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.models import Base
from api.knowledge import models as knowledge_models

assert knowledge_models.KnowledgeDocument.metadata is Base.metadata


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def vector_database() -> AsyncGenerator[
    tuple[async_sessionmaker[AsyncSession], str], None
]:
    raw = os.getenv("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set TEST_DATABASE_URL to run pgvector integration checks")
    url = make_url(raw).set(drivername="postgresql+psycopg")
    admin = create_async_engine(url)
    schema = f"rf_knowledge_{uuid4().hex}"
    try:
        async with admin.begin() as connection:
            await connection.execute(
                text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
            )
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        scoped = url.update_query_dict({"options": f"-csearch_path={schema},public"})
        engine = create_async_engine(scoped)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            yield (
                async_sessionmaker(engine, expire_on_commit=False),
                scoped.render_as_string(hide_password=False),
            )
        finally:
            await engine.dispose()
    finally:
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()
