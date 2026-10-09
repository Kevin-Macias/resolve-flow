import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.db.models import CustomerAccount
from api.knowledge.chunks import CHUNK_STRATEGY, CHUNK_STRATEGY_VERSION, prepare_chunks
from api.knowledge.embeddings import EmbeddingError, EmbeddingFailure
from api.knowledge.markdown import MarkdownDocument, load_manifest, prepare_markdown
from api.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeEmbedding
from api.knowledge.postgres_retriever import PostgresChunkIndexer, PostgresRetriever
from api.knowledge.postgres_store import PostgresDocumentStore
from api.knowledge.retrieval import (
    DocumentRevision,
    RetrievalError,
    RetrievalFailure,
    RetrievalRequest,
    RetrievalScope,
    RetrievalService,
)

ROOT = Path(__file__).resolve().parents[4]


class DeterministicEmbeddings:
    profile = "test:1536:v1"

    def __init__(self, failure: Exception | None = None, invalid: bool = False) -> None:
        self.failure = failure
        self.invalid = invalid
        self.document_calls: list[tuple[str, ...]] = []
        self.query_calls: list[str] = []

    async def embed_documents(self, texts: tuple[str, ...]) -> list[list[float]]:
        self.document_calls.append(texts)
        if self.failure:
            raise self.failure
        return [[1.0] + [0.0] * (1535 if not self.invalid else 1) for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        if self.failure:
            raise self.failure
        return [1.0] + [0.0] * 1535


def document(**changes: Any) -> MarkdownDocument:
    meta = load_manifest(ROOT / "knowledge/manifest.json")[0]
    return prepare_markdown(ROOT, meta.model_copy(update=changes))


def request(docs: tuple[MarkdownDocument, ...], **changes: Any) -> RetrievalRequest:
    return RetrievalRequest.model_validate(
        {
            "query": "Where is my report?",
            "scope": RetrievalScope(allow_internal=True),
            "active_revisions": tuple(
                DocumentRevision(
                    document_id=doc.metadata.document_id, version=doc.metadata.version
                )
                for doc in docs
            ),
            "top_k": 20,
        }
        | changes
    )


async def counts(sessions: async_sessionmaker[AsyncSession]) -> tuple[int, int]:
    async with sessions() as session:
        return (
            int(
                await session.scalar(select(func.count()).select_from(KnowledgeChunk))
                or 0
            ),
            int(
                await session.scalar(
                    select(func.count()).select_from(KnowledgeEmbedding)
                )
                or 0
            ),
        )


@pytest.mark.anyio
async def test_index_roundtrip_idempotency_and_exact_search(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    docs = tuple(
        prepare_markdown(ROOT, m)
        for m in load_manifest(ROOT / "knowledge/manifest.json")
    )
    provider = DeterministicEmbeddings()
    await PostgresDocumentStore(sessions).commit_batch(docs)
    indexer = PostgresChunkIndexer(sessions, provider)
    assert await indexer.index_documents(docs) == 31
    assert await PostgresChunkIndexer(sessions, provider).index_documents(docs) == 0
    assert len(provider.document_calls) == 1
    assert await counts(sessions) == (31, 31)
    # Exclude the superseded legacy guide despite its matching vector.
    result = await RetrievalService(PostgresRetriever(sessions, provider)).search(
        request(docs)
    )
    assert len(result.evidence) == 20
    assert all(item.metadata.status == "current" for item in result.evidence)
    assert all(item.score == pytest.approx(1) for item in result.evidence)
    assert [str(item.chunk_id) for item in result.evidence] == sorted(
        str(item.chunk_id) for item in result.evidence
    )
    prepared = {c.chunk_id: c for doc in docs for c in prepare_chunks(doc)}
    for item in result.evidence:
        assert item.text == prepared[item.chunk_id].text
        assert item.passage == prepared[item.chunk_id].passage
    assert any(item.metadata.fictional for item in result.evidence)


@pytest.mark.anyio
async def test_sql_filters_precede_limit(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    account, other = uuid4(), uuid4()
    async with sessions() as session, session.begin():
        session.add_all(
            [
                CustomerAccount(id=account, name="Permitted"),
                CustomerAccount(id=other, name="Other"),
            ]
        )
    docs = (
        document(document_id="public", access_class="PUBLIC"),
        document(
            document_id="mine",
            access_class="CUSTOMER_ACCOUNT",
            customer_account_id=account,
        ),
        document(
            document_id="other-account",
            access_class="CUSTOMER_ACCOUNT",
            customer_account_id=other,
        ),
        document(document_id="internal"),
        document(document_id="stale", status="superseded", superseded_by="public"),
        document(document_id="different-service", service_code="other"),
        document(document_id="inactive"),
        document(document_id="old", version="old"),
    )
    provider = DeterministicEmbeddings()
    await PostgresDocumentStore(sessions).commit_batch(docs)
    await PostgresChunkIndexer(sessions, provider).index_documents(docs)
    async with sessions() as session, session.begin():
        permitted = (
            select(KnowledgeChunk.id)
            .join(KnowledgeDocument)
            .where(KnowledgeDocument.document_id.in_(["public", "mine"]))
        )
        await session.execute(
            update(KnowledgeEmbedding)
            .where(KnowledgeEmbedding.chunk_id.in_(permitted))
            .values(embedding=[0.0, 1.0] + [0.0] * 1534)
        )
    active = tuple(
        DocumentRevision(document_id=doc.metadata.document_id, version="1")
        for doc in docs
        if doc.metadata.document_id != "inactive"
    )
    search = request(
        (),
        active_revisions=active,
        scope=RetrievalScope(customer_account_ids=frozenset({account})),
        service_code="issue-reports",
        top_k=2,
    )
    result = await RetrievalService(PostgresRetriever(sessions, provider)).search(
        search
    )
    assert len(result.evidence) == 2
    assert all(
        item.metadata.document_id in {"public", "mine"} for item in result.evidence
    )
    assert all(item.score == pytest.approx(0) for item in result.evidence)
    support = search.model_copy(
        update={"scope": RetrievalScope(allow_internal=True), "top_k": 20}
    )
    result = await RetrievalService(PostgresRetriever(sessions, provider)).search(
        support
    )
    assert {item.metadata.document_id for item in result.evidence} == {
        "public",
        "internal",
    }
    assert result.evidence[0].metadata.document_id == "internal"


@pytest.mark.anyio
async def test_cosine_conversion_profile_and_strategy_exclusions(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    doc = document()
    provider = DeterministicEmbeddings()
    await PostgresDocumentStore(sessions).commit_batch((doc,))
    await PostgresChunkIndexer(sessions, provider).index_documents((doc,))
    chunks = prepare_chunks(doc)
    async with sessions() as session, session.begin():
        for chunk, vector in zip(
            chunks[:3], [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]], strict=True
        ):
            await session.execute(
                update(KnowledgeEmbedding)
                .where(KnowledgeEmbedding.chunk_id == chunk.chunk_id)
                .values(embedding=vector + [0.0] * 1534)
            )
        await session.execute(
            update(KnowledgeEmbedding)
            .where(KnowledgeEmbedding.chunk_id == chunks[3].chunk_id)
            .values(profile="incompatible:1536:v1")
        )
        revision = await session.scalar(select(KnowledgeDocument.id))
        incompatible = KnowledgeChunk(
            document_revision_id=revision,
            strategy=CHUNK_STRATEGY,
            strategy_version="future",
            ordinal=0,
            chunk_text="Exclude this",
            source_location=chunks[0].passage.location.model_dump(mode="json"),
        )
        session.add(incompatible)
        await session.flush()
        session.add(
            KnowledgeEmbedding(
                chunk_id=incompatible.id,
                profile=provider.profile,
                embedding=[1.0] + [0.0] * 1535,
            )
        )
    result = await RetrievalService(PostgresRetriever(sessions, provider)).search(
        request((doc,))
    )
    assert [item.chunk_id for item in result.evidence] == [
        chunk.chunk_id for chunk in chunks[:3]
    ]
    assert [item.score for item in result.evidence] == pytest.approx([1, 0, -1])
    # Adding a compatible profile does not duplicate chunks or overwrite other profiles.
    assert await PostgresChunkIndexer(sessions, provider).index_documents((doc,)) == 1
    assert await counts(sessions) == (5, 6)


@pytest.mark.anyio
@pytest.mark.parametrize("invalid", [False, True])
async def test_provider_failure_leaves_no_passages(
    vector_database: tuple[async_sessionmaker[AsyncSession], str], invalid: bool
) -> None:
    sessions, _ = vector_database
    doc = document()
    await PostgresDocumentStore(sessions).commit_batch((doc,))
    provider = DeterministicEmbeddings(
        invalid=invalid, failure=None if invalid else RuntimeError("secret")
    )
    with pytest.raises(EmbeddingError):
        await PostgresChunkIndexer(sessions, provider).index_documents((doc,))
    assert await counts(sessions) == (0, 0)


@pytest.mark.anyio
async def test_write_conflict_rolls_back_and_concurrent_index_is_idempotent(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    doc = document()
    chunks = prepare_chunks(doc)
    await PostgresDocumentStore(sessions).commit_batch((doc,))
    # A conflicting positional identity sorts last so earlier inserts must roll back.
    conflicting = max(chunks, key=lambda chunk: str(chunk.chunk_id))
    async with sessions() as session, session.begin():
        revision = await session.scalar(select(KnowledgeDocument.id))
        session.add(
            KnowledgeChunk(
                document_revision_id=revision,
                strategy=CHUNK_STRATEGY,
                strategy_version=CHUNK_STRATEGY_VERSION,
                ordinal=conflicting.ordinal,
                chunk_text="conflicting text",
                source_location=conflicting.passage.location.model_dump(mode="json"),
            )
        )
    with pytest.raises(EmbeddingError) as error:
        await PostgresChunkIndexer(sessions, DeterministicEmbeddings()).index_documents(
            (doc,)
        )
    assert error.value.reason == EmbeddingFailure.CONFLICT
    assert await counts(sessions) == (1, 0)
    async with sessions() as session, session.begin():
        await session.execute(text("DELETE FROM knowledge_chunks"))
    indexer = PostgresChunkIndexer(sessions, DeterministicEmbeddings())
    results = await asyncio.gather(
        indexer.index_documents((doc,)), indexer.index_documents((doc,))
    )
    assert sum(results) == 4
    assert await counts(sessions) == (4, 4)
    altered = prepare_markdown(
        ROOT, doc.metadata.model_copy(update={"title": "Different"})
    )
    with pytest.raises(EmbeddingError) as error:
        await indexer.index_documents((altered,))
    assert error.value.reason == EmbeddingFailure.CONFLICT


@pytest.mark.anyio
async def test_empty_budget_and_query_failure(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    provider = DeterministicEmbeddings()
    service = RetrievalService(PostgresRetriever(sessions, provider))
    assert (await service.search(request(()))).evidence == ()
    assert provider.query_calls == []
    with pytest.raises(RetrievalError) as error:
        await service.search(request((), query=" hello" * 513))
    assert error.value.reason == RetrievalFailure.INVALID_INPUT
    provider.failure = TimeoutError("secret")
    with pytest.raises(RetrievalError) as error:
        await service.search(request((document(),)))
    assert error.value.reason == RetrievalFailure.TIMEOUT
    assert "secret" not in str(error.value)


@pytest.mark.anyio
async def test_baseline_preflight_is_read_only_and_rejects_incomplete_index(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    from api.knowledge.postgres_retriever import verify_indexed_corpus

    sessions, _ = vector_database
    doc = document()
    provider = DeterministicEmbeddings()
    await PostgresDocumentStore(sessions).commit_batch((doc,))
    with pytest.raises(EmbeddingError) as error:
        await verify_indexed_corpus(sessions, (doc,), provider.profile)
    assert error.value.reason == EmbeddingFailure.CONFLICT
    assert await counts(sessions) == (0, 0)
    await PostgresChunkIndexer(sessions, provider).index_documents((doc,))
    before = await counts(sessions)
    await verify_indexed_corpus(sessions, (doc,), provider.profile)
    assert await counts(sessions) == before
    assert len(provider.document_calls) == 1
    with pytest.raises(EmbeddingError):
        await verify_indexed_corpus(sessions, (doc,), "unindexed:1536:v1")
    assert await counts(sessions) == before
    async with sessions() as session, session.begin():
        await session.execute(
            update(KnowledgeChunk).values(chunk_text="changed passage")
        )
    with pytest.raises(EmbeddingError):
        await verify_indexed_corpus(sessions, (doc,), provider.profile)
    assert await counts(sessions) == before


@pytest.mark.anyio
async def test_successful_empty_filtered_search_over_indexed_corpus(
    vector_database: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    sessions, _ = vector_database
    doc = document()
    provider = DeterministicEmbeddings()
    await PostgresDocumentStore(sessions).commit_batch((doc,))
    await PostgresChunkIndexer(sessions, provider).index_documents((doc,))
    service = RetrievalService(PostgresRetriever(sessions, provider))
    assert (
        await service.search(request((doc,), service_code="other-service"))
    ).evidence == ()
    assert (
        await service.search(request((doc,), scope=RetrievalScope()))
    ).evidence == ()
    assert len(provider.query_calls) == 2
