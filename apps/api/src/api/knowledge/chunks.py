"""Prepare exact heading sections with deterministic identities and input budgets."""

import json
import re
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field

from api.knowledge.embeddings import EmbeddingError, EmbeddingFailure, validate_input
from api.knowledge.markdown import MarkdownDocument, parse_sections
from api.knowledge.metadata import DocumentMetadata, KnowledgeContract, PassageLocation

CHUNK_STRATEGY = "markdown-heading"
CHUNK_STRATEGY_VERSION = "1"


class PreparedChunk(KnowledgeContract):
    chunk_id: UUID
    ordinal: Annotated[int, Field(strict=True, ge=0)]
    text: str
    embedding_input: str
    metadata: DocumentMetadata
    passage: PassageLocation


def prepare_chunks(document: MarkdownDocument) -> tuple[PreparedChunk, ...]:
    document = MarkdownDocument.model_validate(document)
    # Do not accept stored section text or locations that disagree with the source.
    if document.sections != parse_sections(document.text, document.metadata):
        raise EmbeddingError(EmbeddingFailure.INVALID_INPUT)
    chunks: list[PreparedChunk] = []
    for section in document.sections:
        lines = [line.strip() for line in section.text.splitlines() if line.strip()]
        editorial_only = (
            len(lines) == 2
            and re.fullmatch(r"#\s+.+", lines[0]) is not None
            and re.fullmatch(
                r"Intended visibility: (PUBLIC|INTERNAL|CUSTOMER_ACCOUNT)\. "
                r"Source version: [^.]+\. Authored: \d{4}-\d{2}-\d{2}\.",
                lines[1],
            )
            is not None
        )
        if not section.text.strip() or editorial_only:
            continue
        ordinal = len(chunks)
        identity = json.dumps(
            [
                document.metadata.document_id,
                document.metadata.version,
                CHUNK_STRATEGY,
                CHUNK_STRATEGY_VERSION,
                ordinal,
            ],
            separators=(",", ":"),
        )
        payload = f"{document.metadata.title}\n\n{section.text}"
        validate_input(payload)
        chunks.append(
            PreparedChunk(
                chunk_id=uuid5(NAMESPACE_URL, identity),
                ordinal=ordinal,
                text=section.text,
                embedding_input=payload,
                metadata=document.metadata,
                passage=section.location,
            )
        )
    return tuple(chunks)
