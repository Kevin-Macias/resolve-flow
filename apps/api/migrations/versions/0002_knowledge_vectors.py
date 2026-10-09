"""Persist knowledge revisions, chunks, and 1536-dimensional vectors.

Revision ID: 0002
Revises: 0001
SQL is a frozen schema snapshot, independent of future ORM changes.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

STATEMENTS = (
    """
CREATE TABLE knowledge_documents (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    document_id TEXT NOT NULL, 
    version TEXT NOT NULL, 
    metadata_record JSONB NOT NULL, 
    source_text TEXT NOT NULL, 
    sections JSONB NOT NULL, 
    content_hash TEXT NOT NULL, 
    metadata_hash TEXT NOT NULL, 
    access_class TEXT NOT NULL, 
    customer_account_id UUID, 
    service_code TEXT NOT NULL, 
    source_status TEXT NOT NULL, 
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_knowledge_documents PRIMARY KEY (id), 
    CONSTRAINT uq_knowledge_documents_revision UNIQUE (document_id, version), 
    CONSTRAINT ck_knowledge_documents_access_class CHECK (access_class IN ('PUBLIC', 'INTERNAL', 'CUSTOMER_ACCOUNT')), 
    CONSTRAINT ck_knowledge_documents_account_scope CHECK ((access_class = 'CUSTOMER_ACCOUNT') = (customer_account_id IS NOT NULL)), 
    CONSTRAINT ck_knowledge_documents_source_status CHECK (source_status IN ('current', 'superseded')), 
    CONSTRAINT ck_knowledge_documents_hashes CHECK (content_hash ~ '^[0-9a-f]{64}$' AND metadata_hash ~ '^[0-9a-f]{64}$'), 
    CONSTRAINT ck_knowledge_documents_identity CHECK (btrim(document_id) <> '' AND btrim(version) <> '' AND btrim(service_code) <> ''), 
    CONSTRAINT ck_knowledge_documents_metadata_binding CHECK (metadata_record->>'document_id' IS NOT NULL AND metadata_record->>'document_id' = document_id AND metadata_record->>'version' IS NOT NULL AND metadata_record->>'version' = version AND metadata_record->>'access_class' IS NOT NULL AND metadata_record->>'access_class' = access_class AND metadata_record->>'service_code' IS NOT NULL AND metadata_record->>'service_code' = service_code AND metadata_record->>'status' IS NOT NULL AND metadata_record->>'status' = source_status AND (metadata_record->>'customer_account_id') IS NOT DISTINCT FROM customer_account_id::text), 
    CONSTRAINT fk_knowledge_documents_customer_account_id_customer_accounts FOREIGN KEY(customer_account_id) REFERENCES customer_accounts (id) ON DELETE RESTRICT
)
    """,
    """
CREATE INDEX ix_knowledge_documents_access_class ON knowledge_documents (access_class)
    """,
    """
CREATE INDEX ix_knowledge_documents_customer_account_id ON knowledge_documents (customer_account_id)
    """,
    """
CREATE INDEX ix_knowledge_documents_service_code ON knowledge_documents (service_code)
    """,
    """
CREATE INDEX ix_knowledge_documents_source_status ON knowledge_documents (source_status)
    """,
    """
CREATE TABLE knowledge_chunks (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    document_revision_id UUID NOT NULL, 
    strategy TEXT NOT NULL, 
    strategy_version TEXT NOT NULL, 
    ordinal INTEGER NOT NULL, 
    chunk_text TEXT NOT NULL, 
    source_location JSONB NOT NULL, 
    CONSTRAINT pk_knowledge_chunks PRIMARY KEY (id), 
    CONSTRAINT uq_knowledge_chunks_position UNIQUE (document_revision_id, strategy, strategy_version, ordinal), 
    CONSTRAINT ck_knowledge_chunks_ordinal CHECK (ordinal >= 0), 
    CONSTRAINT ck_knowledge_chunks_content CHECK (btrim(strategy) <> '' AND btrim(strategy_version) <> '' AND btrim(chunk_text) <> ''), 
    CONSTRAINT ck_knowledge_chunks_location CHECK (source_location->>'kind' IS NOT NULL AND source_location->>'kind' = 'markdown' AND source_location->>'line_start' IS NOT NULL AND source_location->>'line_end' IS NOT NULL AND (source_location->>'line_start')::integer >= 1 AND (source_location->>'line_end')::integer >= (source_location->>'line_start')::integer), 
    CONSTRAINT fk_knowledge_chunks_document_revision_id_knowledge_documents FOREIGN KEY(document_revision_id) REFERENCES knowledge_documents (id) ON DELETE RESTRICT
)
    """,
    """
CREATE INDEX ix_knowledge_chunks_document_revision_id ON knowledge_chunks (document_revision_id)
    """,
    """
CREATE TABLE knowledge_embeddings (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    chunk_id UUID NOT NULL, 
    profile TEXT NOT NULL, 
    embedding VECTOR(1536) NOT NULL, 
    CONSTRAINT pk_knowledge_embeddings PRIMARY KEY (id), 
    CONSTRAINT uq_knowledge_embeddings_profile UNIQUE (chunk_id, profile), 
    CONSTRAINT ck_knowledge_embeddings_profile CHECK (btrim(profile) <> ''), 
    CONSTRAINT ck_knowledge_embeddings_nonzero CHECK (vector_norm(embedding) > 0), 
    CONSTRAINT fk_knowledge_embeddings_chunk_id_knowledge_chunks FOREIGN KEY(chunk_id) REFERENCES knowledge_chunks (id) ON DELETE RESTRICT
)
    """,
    """
CREATE INDEX ix_knowledge_embeddings_chunk_id ON knowledge_embeddings (chunk_id)
    """,
    """
CREATE INDEX ix_knowledge_embeddings_profile ON knowledge_embeddings (profile)
    """,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("knowledge_embeddings")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    # vector is database-wide; do not remove another consumer's extension.
