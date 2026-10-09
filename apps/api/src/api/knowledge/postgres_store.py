"""Async transactional ingestion; callers supply trusted prepared documents."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.knowledge.markdown import (
    IngestionError,
    IngestionFailure,
    MarkdownDocument,
    load_manifest,
    prepare_markdown,
)
from api.knowledge.models import KnowledgeDocument
from api.knowledge.store import IngestionResult, IngestionStatus


class PostgresDocumentStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, document_id: str, version: str) -> MarkdownDocument | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.document_id == document_id,
                    KnowledgeDocument.version == version,
                )
            )
            if row is None:
                return None
            return MarkdownDocument.model_validate(
                {
                    "metadata": row.metadata_record,
                    "text": row.source_text,
                    "sections": row.sections,
                    "content_hash": row.content_hash,
                    "metadata_hash": row.metadata_hash,
                }
            )

    async def commit_batch(
        self, documents: tuple[MarkdownDocument, ...]
    ) -> tuple[IngestionResult, ...]:
        # Stable lock acquisition order avoids deadlocks for overlapping batches.
        indexed = sorted(
            enumerate(documents),
            key=lambda item: (item[1].metadata.document_id, item[1].metadata.version),
        )
        results: dict[int, IngestionResult] = {}
        async with self._sessions() as session, session.begin():
            for index, raw in indexed:
                document = MarkdownDocument.model_validate(raw)
                meta = document.metadata
                statement = (
                    insert(KnowledgeDocument)
                    .values(
                        document_id=meta.document_id,
                        version=meta.version,
                        metadata_record=meta.model_dump(mode="json"),
                        source_text=document.text,
                        sections=[s.model_dump(mode="json") for s in document.sections],
                        content_hash=document.content_hash,
                        metadata_hash=document.metadata_hash,
                        access_class=meta.access_class.value,
                        customer_account_id=meta.customer_account_id,
                        service_code=meta.service_code,
                        source_status=meta.status.value,
                    )
                    .on_conflict_do_nothing(index_elements=["document_id", "version"])
                    .returning(KnowledgeDocument.id)
                )
                created = await session.scalar(statement)
                if created is None:
                    saved = await session.scalar(
                        select(KnowledgeDocument).where(
                            KnowledgeDocument.document_id == meta.document_id,
                            KnowledgeDocument.version == meta.version,
                        )
                    )
                    if (
                        saved is None
                        or saved.content_hash != document.content_hash
                        or saved.metadata_hash != document.metadata_hash
                    ):
                        raise IngestionError(IngestionFailure.VERSION_CONFLICT)
                results[index] = IngestionResult(
                    document_id=meta.document_id,
                    version=meta.version,
                    status=IngestionStatus.CREATED
                    if created is not None
                    else IngestionStatus.UNCHANGED,
                )
        return tuple(results[index] for index in range(len(documents)))


async def ingest_manifest_postgres(
    root: Path, manifest: Path, store: PostgresDocumentStore
) -> tuple[IngestionResult, ...]:
    # File work is intentionally off the event loop; database operations stay async.
    import asyncio

    def prepare() -> tuple[MarkdownDocument, ...]:
        return tuple(prepare_markdown(root, entry) for entry in load_manifest(manifest))

    documents = await asyncio.to_thread(prepare)
    return await store.commit_batch(documents)
