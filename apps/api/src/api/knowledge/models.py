"""Relational knowledge revisions and future searchable passage vectors."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models import Base
from api.knowledge.embeddings import EMBEDDING_DIMENSIONS as EMBEDDING_DIMENSIONS
from api.knowledge.embeddings import EMBEDDING_PROFILE as EMBEDDING_PROFILE


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version", name="uq_knowledge_documents_revision"
        ),
        CheckConstraint(
            "access_class IN ('PUBLIC', 'INTERNAL', 'CUSTOMER_ACCOUNT')",
            name="access_class",
        ),
        CheckConstraint(
            "(access_class = 'CUSTOMER_ACCOUNT') = (customer_account_id IS NOT NULL)",
            name="account_scope",
        ),
        CheckConstraint(
            "source_status IN ('current', 'superseded')", name="source_status"
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$' AND metadata_hash ~ '^[0-9a-f]{64}$'",
            name="hashes",
        ),
        CheckConstraint(
            "btrim(document_id) <> '' AND btrim(version) <> '' AND btrim(service_code) <> ''",
            name="identity",
        ),
        CheckConstraint(
            "metadata_record->>'document_id' IS NOT NULL AND metadata_record->>'document_id' = document_id AND metadata_record->>'version' IS NOT NULL AND metadata_record->>'version' = version AND metadata_record->>'access_class' IS NOT NULL AND metadata_record->>'access_class' = access_class AND metadata_record->>'service_code' IS NOT NULL AND metadata_record->>'service_code' = service_code AND metadata_record->>'status' IS NOT NULL AND metadata_record->>'status' = source_status AND (metadata_record->>'customer_account_id') IS NOT DISTINCT FROM customer_account_id::text",
            name="metadata_binding",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_record: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_hash: Mapped[str] = mapped_column(Text, nullable=False)
    access_class: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    customer_account_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_accounts.id", ondelete="RESTRICT"),
        index=True,
    )
    service_code: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    source_status: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_revision_id",
            "strategy",
            "strategy_version",
            "ordinal",
            name="uq_knowledge_chunks_position",
        ),
        CheckConstraint("ordinal >= 0", name="ordinal"),
        CheckConstraint(
            "btrim(strategy) <> '' AND btrim(strategy_version) <> '' AND btrim(chunk_text) <> ''",
            name="content",
        ),
        CheckConstraint(
            "source_location->>'kind' IS NOT NULL AND source_location->>'kind' = 'markdown' AND source_location->>'line_start' IS NOT NULL AND source_location->>'line_end' IS NOT NULL AND (source_location->>'line_start')::integer >= 1 AND (source_location->>'line_end')::integer >= (source_location->>'line_start')::integer",
            name="location",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_revision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_version: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_location: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class KnowledgeEmbedding(Base):
    __tablename__ = "knowledge_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "profile", name="uq_knowledge_embeddings_profile"),
        CheckConstraint("btrim(profile) <> ''", name="profile"),
        CheckConstraint("vector_norm(embedding) > 0", name="nonzero"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    chunk_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge_chunks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    profile: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=False
    )
