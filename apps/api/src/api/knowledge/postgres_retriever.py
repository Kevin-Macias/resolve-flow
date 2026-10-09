"""Index prepared passages and search existing tables with explicit SQL policy."""

import math

from pydantic import ValidationError
from sqlalchemy import or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.knowledge.chunks import (
    CHUNK_STRATEGY,
    CHUNK_STRATEGY_VERSION,
    PreparedChunk,
    prepare_chunks,
)
from api.knowledge.embeddings import (
    EmbeddingError,
    EmbeddingFailure,
    EmbeddingProvider,
    embed_documents_checked,
    embed_query_checked,
    validate_input,
    validate_profile,
    validate_vector,
)
from api.knowledge.markdown import MarkdownDocument
from api.knowledge.metadata import DocumentMetadata, PassageLocation
from api.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeEmbedding
from api.knowledge.retrieval import (
    RankedEvidence,
    RetrievalError,
    RetrievalFailure,
    RetrievalRequest,
    RetrievalResult,
)


async def checked_revision(
    session: AsyncSession, document: MarkdownDocument
) -> KnowledgeDocument:
    row = await session.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.document_id == document.metadata.document_id,
            KnowledgeDocument.version == document.metadata.version,
        )
    )
    if row is None or (
        row.content_hash != document.content_hash
        or row.metadata_hash != document.metadata_hash
        or row.source_text != document.text
        or row.metadata_record != document.metadata.model_dump(mode="json")
        or row.sections != [s.model_dump(mode="json") for s in document.sections]
    ):
        raise EmbeddingError(EmbeddingFailure.CONFLICT)
    return row


def check_saved_chunk(saved: KnowledgeChunk, prepared: PreparedChunk) -> None:
    if (
        saved.chunk_text != prepared.text
        or saved.source_location != prepared.passage.location.model_dump(mode="json")
        or saved.strategy != CHUNK_STRATEGY
        or saved.strategy_version != CHUNK_STRATEGY_VERSION
        or saved.ordinal != prepared.ordinal
    ):
        raise EmbeddingError(EmbeddingFailure.CONFLICT)


class PostgresChunkIndexer:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], provider: EmbeddingProvider
    ) -> None:
        self._sessions = sessions
        self._provider = provider

    async def index_documents(self, documents: tuple[MarkdownDocument, ...]) -> int:
        """Returns the number of new vectors; source revisions must already exist."""
        documents = tuple(MarkdownDocument.model_validate(doc) for doc in documents)
        identities = [
            (doc.metadata.document_id, doc.metadata.version) for doc in documents
        ]
        if len(identities) != len(set(identities)):
            raise EmbeddingError(EmbeddingFailure.INVALID_INPUT)
        profile = self._provider.profile
        validate_profile(profile)
        prepared = tuple(chunk for doc in documents for chunk in prepare_chunks(doc))
        try:
            missing: list[PreparedChunk] = []
            async with self._sessions() as session:
                revisions = {
                    (doc.metadata.document_id, doc.metadata.version): (
                        await checked_revision(session, doc)
                    ).id
                    for doc in documents
                }
                for chunk in prepared:
                    saved = await session.get(KnowledgeChunk, chunk.chunk_id)
                    if saved is not None:
                        check_saved_chunk(saved, chunk)
                        if (
                            saved.document_revision_id
                            != revisions[
                                (chunk.metadata.document_id, chunk.metadata.version)
                            ]
                        ):
                            raise EmbeddingError(EmbeddingFailure.CONFLICT)
                    exists = await session.scalar(
                        select(KnowledgeEmbedding.id).where(
                            KnowledgeEmbedding.chunk_id == chunk.chunk_id,
                            KnowledgeEmbedding.profile == profile,
                        )
                    )
                    if exists is None:
                        missing.append(chunk)
            # Complete provider work and validate all vectors before starting writes.
            vectors = await embed_documents_checked(
                self._provider, tuple(chunk.embedding_input for chunk in missing)
            )
            if self._provider.profile != profile:
                raise EmbeddingError(EmbeddingFailure.CONFLICT)
            created = 0
            async with self._sessions() as session, session.begin():
                revisions = {
                    (doc.metadata.document_id, doc.metadata.version): (
                        await checked_revision(session, doc)
                    ).id
                    for doc in documents
                }
                # Consistent insertion order protects concurrent overlapping batches.
                pairs = sorted(
                    zip(missing, vectors, strict=True),
                    key=lambda pair: str(pair[0].chunk_id),
                )
                for chunk, vector in pairs:
                    revision_id = revisions[
                        (chunk.metadata.document_id, chunk.metadata.version)
                    ]
                    await session.execute(
                        insert(KnowledgeChunk)
                        .values(
                            id=chunk.chunk_id,
                            document_revision_id=revision_id,
                            strategy=CHUNK_STRATEGY,
                            strategy_version=CHUNK_STRATEGY_VERSION,
                            ordinal=chunk.ordinal,
                            chunk_text=chunk.text,
                            source_location=chunk.passage.location.model_dump(
                                mode="json"
                            ),
                        )
                        .on_conflict_do_nothing()
                    )
                    saved = await session.get(KnowledgeChunk, chunk.chunk_id)
                    if saved is None or saved.document_revision_id != revision_id:
                        raise EmbeddingError(EmbeddingFailure.CONFLICT)
                    check_saved_chunk(saved, chunk)
                    inserted = await session.scalar(
                        insert(KnowledgeEmbedding)
                        .values(
                            chunk_id=chunk.chunk_id,
                            profile=profile,
                            embedding=vector,
                        )
                        .on_conflict_do_nothing(index_elements=["chunk_id", "profile"])
                        .returning(KnowledgeEmbedding.id)
                    )
                    created += int(inserted is not None)
            return created
        except EmbeddingError as error:
            raise EmbeddingError(error.reason) from None
        except Exception:
            raise EmbeddingError(EmbeddingFailure.UNAVAILABLE) from None


class PostgresRetriever:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], provider: EmbeddingProvider
    ) -> None:
        self._sessions = sessions
        self._provider = provider

    async def search(self, request: RetrievalRequest) -> RetrievalResult:
        request = RetrievalRequest.model_validate(request)
        try:
            validate_input(request.query)
            profile = self._provider.profile
            validate_profile(profile)
            if not request.active_revisions:
                return RetrievalResult()
            vector = await embed_query_checked(self._provider, request.query)
            if self._provider.profile != profile:
                raise EmbeddingError(EmbeddingFailure.CONFLICT)
            distance = KnowledgeEmbedding.embedding.cosine_distance(vector).label(
                "distance"
            )
            access = [KnowledgeDocument.access_class == "PUBLIC"]
            if request.scope.allow_internal:
                access.append(KnowledgeDocument.access_class == "INTERNAL")
            if request.scope.customer_account_ids:
                access.append(
                    (KnowledgeDocument.access_class == "CUSTOMER_ACCOUNT")
                    & KnowledgeDocument.customer_account_id.in_(
                        request.scope.customer_account_ids
                    )
                )
            statement = (
                select(KnowledgeChunk, KnowledgeDocument, distance)
                .join(
                    KnowledgeDocument,
                    KnowledgeChunk.document_revision_id == KnowledgeDocument.id,
                )
                .join(
                    KnowledgeEmbedding, KnowledgeEmbedding.chunk_id == KnowledgeChunk.id
                )
                .where(
                    tuple_(
                        KnowledgeDocument.document_id, KnowledgeDocument.version
                    ).in_(
                        [
                            (rev.document_id, rev.version)
                            for rev in request.active_revisions
                        ]
                    ),
                    KnowledgeDocument.source_status == "current",
                    or_(*access),
                    KnowledgeChunk.strategy == CHUNK_STRATEGY,
                    KnowledgeChunk.strategy_version == CHUNK_STRATEGY_VERSION,
                    KnowledgeEmbedding.profile == profile,
                )
            )
            if request.service_code is not None:
                statement = statement.where(
                    KnowledgeDocument.service_code == request.service_code
                )
            statement = statement.order_by(distance, KnowledgeChunk.id).limit(
                request.top_k
            )
            async with self._sessions() as session:
                rows = (await session.execute(statement)).all()
                if any(
                    not math.isfinite(float(row[2]))
                    or not -1e-6 <= float(row[2]) <= 2.000001
                    for row in rows
                ):
                    raise RetrievalError(RetrievalFailure.INVALID_RESPONSE)
                evidence = tuple(
                    RankedEvidence(
                        chunk_id=chunk.id,
                        text=chunk.chunk_text,
                        metadata=DocumentMetadata.model_validate(doc.metadata_record),
                        passage=PassageLocation.model_validate(
                            {
                                "document_id": doc.document_id,
                                "version": doc.version,
                                "location": chunk.source_location,
                            }
                        ),
                        rank=rank,
                        score=max(-1.0, min(1.0, 1.0 - float(raw_distance))),
                        score_metric="cosine_similarity",
                    )
                    for rank, (chunk, doc, raw_distance) in enumerate(rows, start=1)
                )
            return RetrievalResult(evidence=evidence)
        except EmbeddingError as error:
            reason = {
                EmbeddingFailure.INVALID_INPUT: RetrievalFailure.INVALID_INPUT,
                EmbeddingFailure.INPUT_TOO_LONG: RetrievalFailure.INVALID_INPUT,
                EmbeddingFailure.TIMEOUT: RetrievalFailure.TIMEOUT,
                EmbeddingFailure.INVALID_RESPONSE: RetrievalFailure.INVALID_RESPONSE,
            }.get(error.reason, RetrievalFailure.UNAVAILABLE)
            raise RetrievalError(reason) from None
        except ValidationError:
            raise RetrievalError(RetrievalFailure.INVALID_RESPONSE) from None
        except RetrievalError as error:
            raise RetrievalError(error.reason) from None
        except Exception:
            raise RetrievalError(RetrievalFailure.UNAVAILABLE) from None


async def verify_indexed_corpus(
    sessions: async_sessionmaker[AsyncSession],
    documents: tuple[MarkdownDocument, ...],
    profile: str,
) -> None:
    """Read-only preflight: do not mistake incomplete indexing for poor relevance."""
    validate_profile(profile)
    try:
        async with sessions() as session:
            for document in documents:
                revision = await checked_revision(session, document)
                expected = prepare_chunks(document)
                stored = (
                    await session.scalars(
                        select(KnowledgeChunk).where(
                            KnowledgeChunk.document_revision_id == revision.id,
                            KnowledgeChunk.strategy == CHUNK_STRATEGY,
                            KnowledgeChunk.strategy_version == CHUNK_STRATEGY_VERSION,
                        )
                    )
                ).all()
                by_id = {chunk.id: chunk for chunk in stored}
                if set(by_id) != {chunk.chunk_id for chunk in expected}:
                    raise EmbeddingError(EmbeddingFailure.CONFLICT)
                for chunk in expected:
                    check_saved_chunk(by_id[chunk.chunk_id], chunk)
                    vector = await session.scalar(
                        select(KnowledgeEmbedding.embedding).where(
                            KnowledgeEmbedding.chunk_id == chunk.chunk_id,
                            KnowledgeEmbedding.profile == profile,
                        )
                    )
                    if vector is None:
                        raise EmbeddingError(EmbeddingFailure.CONFLICT)
                    validate_vector(vector)
    except EmbeddingError as error:
        raise EmbeddingError(error.reason) from None
    except Exception:
        raise EmbeddingError(EmbeddingFailure.UNAVAILABLE) from None
