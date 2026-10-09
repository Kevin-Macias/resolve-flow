"""Knowledge persistence checks against disposable committed test schemas."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.knowledge.markdown import (
    IngestionError,
    MarkdownDocument,
    load_manifest,
    prepare_markdown,
)
from api.knowledge.models import (
    EMBEDDING_DIMENSIONS,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeEmbedding,
)
from api.knowledge.postgres_store import PostgresDocumentStore
from api.knowledge.store import IngestionStatus

ROOT = Path(__file__).resolve().parents[4]


def document(version: str = "1") -> MarkdownDocument:
    meta = next(
        e
        for e in load_manifest(ROOT / "knowledge/manifest.json")
        if e.document_id == "archived-report"
    )
    return prepare_markdown(ROOT, meta.model_copy(update={"version": version}))


@pytest.mark.anyio
async def test_revision_roundtrip_new_store_and_process_restart(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, url = vector_database
    first = document()
    store = PostgresDocumentStore(sessions)
    assert (await store.commit_batch((first,)))[0].status == IngestionStatus.CREATED
    assert (await PostgresDocumentStore(sessions).commit_batch((first,)))[
        0
    ].status == IngestionStatus.UNCHANGED
    assert await store.get("archived-report", "1") == first
    assert await store.get("missing", "1") is None
    revised = document("2")
    await store.commit_batch((revised,))
    assert await store.get("archived-report", "1") == first
    assert await store.get("archived-report", "2") == revised
    code = """import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from api.knowledge.postgres_store import PostgresDocumentStore
async def main():
    engine = create_async_engine(os.environ["RF405_WORKER_URL"])
    try:
        result = await PostgresDocumentStore(async_sessionmaker(engine)).get("archived-report", "1")
        assert result is not None
        print(result.model_dump_json())
    finally:
        await engine.dispose()
asyncio.run(main())
"""
    environment = dict(
        os.environ, RF405_WORKER_URL=url, PYTHONPATH=str(ROOT / "apps/api/src")
    )
    worker = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert MarkdownDocument.model_validate_json(worker.stdout) == first


@pytest.mark.anyio
async def test_conflict_rolls_back_whole_batch(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    store = PostgresDocumentStore(sessions)
    original = document()
    await store.commit_batch((original,))
    other_meta = original.metadata.model_copy(update={"document_id": "aaa-new"})
    new = prepare_markdown(ROOT, other_meta)
    changed = prepare_markdown(
        ROOT, original.metadata.model_copy(update={"access_class": "PUBLIC"})
    )
    with pytest.raises(IngestionError):
        await store.commit_batch((new, changed))
    assert await store.get("aaa-new", "1") is None
    assert await store.get("archived-report", "1") == original


@pytest.mark.anyio
async def test_concurrent_identical_and_changed_revisions(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    store = PostgresDocumentStore(sessions)
    first = document()
    results = await asyncio.gather(
        store.commit_batch((first,)), store.commit_batch((first,))
    )
    assert sorted(r[0].status.value for r in results) == ["created", "unchanged"]
    next_version = document("2")
    changed = prepare_markdown(
        ROOT, next_version.metadata.model_copy(update={"title": "Different title"})
    )
    competing = await asyncio.gather(
        store.commit_batch((next_version,)),
        store.commit_batch((changed,)),
        return_exceptions=True,
    )
    assert sum(isinstance(r, IngestionError) for r in competing) == 1
    saved = await store.get("archived-report", "2")
    assert saved in (next_version, changed)


async def chunk(sessions: async_sessionmaker[AsyncSession], ordinal: int = 0) -> UUID:
    async with sessions() as session, session.begin():
        revision = await session.scalar(select(KnowledgeDocument.id))
        assert revision is not None
        row = KnowledgeChunk(
            document_revision_id=revision,
            strategy="test-only",
            strategy_version="1",
            ordinal=ordinal,
            chunk_text="Known test passage",
            source_location={
                "kind": "markdown",
                "heading_path": ["Checks"],
                "line_start": 10,
                "line_end": 12,
            },
        )
        session.add(row)
        await session.flush()
        return row.id


@pytest.mark.anyio
async def test_vectors_and_exact_cosine_ordering(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    await PostgresDocumentStore(sessions).commit_batch((document(),))
    ids = [await chunk(sessions, ordinal) for ordinal in range(3)]
    vectors = [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]
    async with sessions() as session, session.begin():
        session.add_all(
            KnowledgeEmbedding(
                chunk_id=identifier,
                profile="test:1536:v1",
                embedding=values + [0.0] * (EMBEDDING_DIMENSIONS - 2),
            )
            for identifier, values in zip(ids, vectors, strict=True)
        )
    query = (
        "["
        + ",".join(str(v) for v in ([1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)))
        + "]"
    )
    async with sessions() as session:
        ordered = (
            await session.execute(
                text(
                    "SELECT chunk_id, embedding <=> CAST(:query AS vector) AS distance FROM knowledge_embeddings WHERE profile = :profile ORDER BY distance, chunk_id"
                ),
                {"query": query, "profile": "test:1536:v1"},
            )
        ).all()
        assert [row[0] for row in ordered] == ids
        assert [row[1] for row in ordered] == pytest.approx([0, 1, 2])
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM pg_indexes WHERE schemaname = current_schema() AND (indexdef LIKE '%USING hnsw%' OR indexdef LIKE '%USING ivfflat%')"
                )
            )
            == 0
        )
    with pytest.raises(IntegrityError):
        async with sessions() as session, session.begin():
            session.add(
                KnowledgeEmbedding(
                    chunk_id=ids[0],
                    profile="test:1536:v1",
                    embedding=[1.0] * EMBEDDING_DIMENSIONS,
                )
            )


@pytest.mark.anyio
@pytest.mark.parametrize("vector", [[1.0, 2.0], [0.0] * EMBEDDING_DIMENSIONS])
async def test_invalid_vectors_rejected(
    vector_database: tuple[async_sessionmaker[AsyncSession], str], vector: list[float]
) -> None:
    sessions, _ = vector_database
    await PostgresDocumentStore(sessions).commit_batch((document(),))
    identifier = await chunk(sessions)
    # The adapter or PostgreSQL may reject an invalid dimension first.
    from sqlalchemy.exc import StatementError

    with pytest.raises((DBAPIError, StatementError)):
        async with sessions() as session, session.begin():
            session.add(
                KnowledgeEmbedding(
                    chunk_id=identifier, profile="test:1536:v1", embedding=vector
                )
            )


@pytest.mark.anyio
async def test_database_constraints_block_invalid_access_and_foreign_keys(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    await PostgresDocumentStore(sessions).commit_batch((document(),))
    for sql in [
        "UPDATE knowledge_documents SET access_class = 'CUSTOMER_ACCOUNT'",
        "UPDATE knowledge_documents SET access_class = 'PUBLIC'",
        "UPDATE knowledge_documents SET customer_account_id = gen_random_uuid()",
    ]:
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                await session.execute(text(sql))
    with pytest.raises(IntegrityError):
        async with sessions() as session, session.begin():
            session.add(
                KnowledgeChunk(
                    document_revision_id=uuid4(),
                    strategy="test",
                    strategy_version="1",
                    ordinal=0,
                    chunk_text="text",
                    source_location={
                        "kind": "markdown",
                        "line_start": 1,
                        "line_end": 1,
                    },
                )
            )


def test_migration_upgrade_downgrade_roundtrip() -> None:
    from psycopg import connect, sql

    raw = os.getenv("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set TEST_DATABASE_URL to run migration checks")
    schema = f"rf_migration_{uuid4().hex}"
    url = make_url(raw)
    with connect(
        url.render_as_string(hide_password=False), autocommit=True
    ) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            scoped = url.update_query_dict(
                {"options": f"-csearch_path={schema},public"}
            )
            env = dict(
                os.environ, DATABASE_URL=scoped.render_as_string(hide_password=False)
            )
            for target in ["head", "0001", "head", "base"]:
                action = "upgrade" if target == "head" else "downgrade"
                subprocess.run(
                    [sys.executable, "-m", "alembic", action, target],
                    cwd=ROOT / "apps/api",
                    env=env,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                exists = connection.execute(
                    "SELECT to_regclass(%s)", (f"{schema}.knowledge_embeddings",)
                ).fetchone()
                assert exists is not None and (exists[0] is not None) == (
                    target == "head"
                )
            assert connection.execute(
                "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
            ).fetchone() == (1,)
        finally:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.mark.anyio
async def test_real_manifest_durable_ingestion(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    from api.knowledge.postgres_store import ingest_manifest_postgres

    sessions, _ = vector_database
    store = PostgresDocumentStore(sessions)
    first = await ingest_manifest_postgres(
        ROOT, ROOT / "knowledge/manifest.json", store
    )
    second = await ingest_manifest_postgres(
        ROOT, ROOT / "knowledge/manifest.json", store
    )
    assert len(first) == len(second) == 8
    assert all(r.status == IngestionStatus.CREATED for r in first)
    assert all(r.status == IngestionStatus.UNCHANGED for r in second)
    for metadata in load_manifest(ROOT / "knowledge/manifest.json"):
        assert await store.get(
            metadata.document_id, metadata.version
        ) == prepare_markdown(ROOT, metadata)


@pytest.mark.anyio
async def test_chunk_identity_and_location_constraints(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    await PostgresDocumentStore(sessions).commit_batch((document(),))
    await chunk(sessions)
    with pytest.raises(IntegrityError):
        await chunk(sessions)
    async with sessions() as session:
        revision = await session.scalar(select(KnowledgeDocument.id))
        assert revision is not None
    for location in [
        {},
        {"kind": "markdown", "line_start": 0, "line_end": 1},
        {"kind": "markdown", "line_start": 2, "line_end": 1},
    ]:
        with pytest.raises(IntegrityError):
            async with sessions() as session, session.begin():
                session.add(
                    KnowledgeChunk(
                        document_revision_id=revision,
                        strategy="test",
                        strategy_version="1",
                        ordinal=1,
                        chunk_text="text",
                        source_location=location,
                    )
                )
