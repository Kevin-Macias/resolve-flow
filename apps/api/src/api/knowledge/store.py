"""Atomic in-memory revision storage; durable persistence belongs to RF-405."""

from enum import StrEnum
from pathlib import Path
from typing import Protocol

from api.knowledge.markdown import (
    IngestionError,
    IngestionFailure,
    MarkdownDocument,
    load_manifest,
    prepare_markdown,
)
from api.knowledge.metadata import KnowledgeContract


class IngestionStatus(StrEnum):
    CREATED = "created"
    UNCHANGED = "unchanged"


class IngestionResult(KnowledgeContract):
    document_id: str
    version: str
    status: IngestionStatus


class DocumentStore(Protocol):
    def commit_batch(
        self, documents: tuple[MarkdownDocument, ...]
    ) -> tuple[IngestionResult, ...]:
        """Commit all revisions or none; reject changes to an existing revision."""
        ...


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], MarkdownDocument] = {}

    def get(self, document_id: str, version: str) -> MarkdownDocument | None:
        return self._documents.get((document_id, version))

    def commit_batch(
        self, documents: tuple[MarkdownDocument, ...]
    ) -> tuple[IngestionResult, ...]:
        pending = dict(self._documents)
        results: list[IngestionResult] = []
        for document in documents:
            document = MarkdownDocument.model_validate(document)
            key = (document.metadata.document_id, document.metadata.version)
            existing = pending.get(key)
            if existing is not None and (
                existing.content_hash != document.content_hash
                or existing.metadata_hash != document.metadata_hash
            ):
                raise IngestionError(IngestionFailure.VERSION_CONFLICT)
            status = IngestionStatus.UNCHANGED if existing else IngestionStatus.CREATED
            if existing is None:
                pending[key] = document
            results.append(
                IngestionResult(document_id=key[0], version=key[1], status=status)
            )
        self._documents = pending
        return tuple(results)


def ingest_manifest(
    root: Path, manifest: Path, store: DocumentStore
) -> tuple[IngestionResult, ...]:
    entries = load_manifest(manifest)
    documents = tuple(prepare_markdown(root, entry) for entry in entries)
    return store.commit_batch(documents)
