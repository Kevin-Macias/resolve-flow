"""Source-backed citation assembly; semantic claim support remains human-reviewed."""

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, ValidationError, model_validator

from api.knowledge.markdown import MarkdownDocument, parse_sections
from api.knowledge.metadata import (
    DocumentMetadata,
    KnowledgeContract,
    PassageLocation,
    Text,
)
from api.knowledge.retrieval import (
    RankedEvidence,
    RetrievalRequest,
    RetrievalResult,
    is_eligible,
)

type SourceHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ClaimKind(StrEnum):
    SUPPORTED = "supported"
    INFERENCE = "inference"
    MISSING_EVIDENCE = "missing_evidence"
    CONFLICT = "conflict"


class EvidenceRole(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


class EvidenceReference(KnowledgeContract):
    chunk_id: UUID
    role: EvidenceRole


class ClaimDraft(KnowledgeContract):
    claim_id: Text
    statement: Text
    kind: ClaimKind
    explanation: Text | None = None
    references: tuple[EvidenceReference, ...] = ()

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        pairs = [(ref.chunk_id, ref.role) for ref in self.references]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Claim references must have unique chunk/role pairs")
        roles = {ref.role for ref in self.references}
        if self.kind != ClaimKind.SUPPORTED and self.explanation is None:
            raise ValueError(
                "Interpretations, gaps, and conflicts require explanations"
            )
        if (
            self.kind != ClaimKind.MISSING_EVIDENCE
            and EvidenceRole.SUPPORTS not in roles
        ):
            raise ValueError("This claim category requires supporting evidence")
        if self.kind == ClaimKind.CONFLICT:
            if EvidenceRole.CONTRADICTS not in roles:
                raise ValueError("Conflicts require contradicting evidence")
        elif self.kind != ClaimKind.INFERENCE and EvidenceRole.CONTRADICTS in roles:
            raise ValueError("Use an inference or conflict for opposing evidence")
        return self


def citation_identity(chunk_id: UUID, content_hash: str, metadata_hash: str) -> UUID:
    identity = json.dumps(
        ["citation-v1", str(chunk_id), content_hash, metadata_hash],
        separators=(",", ":"),
    )
    return uuid5(NAMESPACE_URL, identity)


class Citation(KnowledgeContract):
    citation_id: UUID
    chunk_id: UUID
    metadata: DocumentMetadata
    passage: PassageLocation
    excerpt: Annotated[str, Field(strict=True, min_length=1)]
    content_hash: SourceHash
    metadata_hash: SourceHash

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        if (self.metadata.document_id, self.metadata.version) != (
            self.passage.document_id,
            self.passage.version,
        ):
            raise ValueError("Citation metadata and passage revisions must agree")
        if self.citation_id != citation_identity(
            self.chunk_id, self.content_hash, self.metadata_hash
        ):
            raise ValueError("Citation identity must bind its chunk and source hashes")
        if not self.excerpt.strip():
            raise ValueError("Citation excerpt cannot be blank")
        return self


class AttributedCitation(KnowledgeContract):
    role: EvidenceRole
    citation: Citation


class CitedClaim(KnowledgeContract):
    draft: ClaimDraft
    citations: tuple[AttributedCitation, ...]

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        expected = [(ref.chunk_id, ref.role) for ref in self.draft.references]
        actual = [(item.citation.chunk_id, item.role) for item in self.citations]
        if actual != expected:
            raise ValueError("Resolved citations must match the claim references")
        return self


class CitationReport(KnowledgeContract):
    claims: tuple[CitedClaim, ...] = ()

    @model_validator(mode="after")
    def validate_claim_ids(self) -> Self:
        identities = [claim.draft.claim_id for claim in self.claims]
        if len(identities) != len(set(identities)):
            raise ValueError("Claim identities must be unique")
        return self


class CitationFailure(StrEnum):
    INVALID_INPUT = "invalid_input"
    INELIGIBLE_EVIDENCE = "ineligible_evidence"
    UNKNOWN_REFERENCE = "unknown_reference"
    SOURCE_UNAVAILABLE = "source_unavailable"
    SOURCE_MISMATCH = "source_mismatch"


class CitationError(ValueError):
    def __init__(self, reason: CitationFailure) -> None:
        self.reason = reason
        super().__init__(f"Citation assembly failed: {reason.value}")


def verify_source(document: MarkdownDocument) -> None:
    canonical = json.dumps(
        document.metadata.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    if (
        document.content_hash
        != hashlib.sha256(document.text.encode("utf-8")).hexdigest()
        or document.metadata_hash
        != hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        or document.sections != parse_sections(document.text, document.metadata)
    ):
        raise CitationError(CitationFailure.SOURCE_MISMATCH)


def _passage_citation(evidence: RankedEvidence, source: MarkdownDocument) -> Citation:
    """Resolve exact source values after source integrity has been verified."""
    if evidence.metadata != source.metadata or not any(
        section.location == evidence.passage and section.text == evidence.text
        for section in source.sections
    ):
        raise CitationError(CitationFailure.SOURCE_MISMATCH)
    return Citation(
        citation_id=citation_identity(
            evidence.chunk_id, source.content_hash, source.metadata_hash
        ),
        chunk_id=evidence.chunk_id,
        metadata=source.metadata,
        passage=evidence.passage,
        excerpt=evidence.text,
        content_hash=source.content_hash,
        metadata_hash=source.metadata_hash,
    )


def _check_eligibility(request: RetrievalRequest, result: RetrievalResult) -> None:
    if len(result.evidence) > request.top_k or any(
        not is_eligible(item.metadata, request) for item in result.evidence
    ):
        raise CitationError(CitationFailure.INELIGIBLE_EVIDENCE)


def verify_evidence_catalog(
    request: RetrievalRequest,
    result: RetrievalResult,
    sources: tuple[MarkdownDocument, ...],
) -> tuple[Citation, ...]:
    """Verify every passage before model input, without inventing claim support."""
    try:
        request = RetrievalRequest.model_validate(request)
        result = RetrievalResult.model_validate(result)
        sources = tuple(MarkdownDocument.model_validate(source) for source in sources)
        _check_eligibility(request, result)
        by_revision = {
            (source.metadata.document_id, source.metadata.version): source
            for source in sources
        }
        if len(by_revision) != len(sources):
            raise CitationError(CitationFailure.INVALID_INPUT)
        verified: set[tuple[str, str]] = set()
        catalog: list[Citation] = []
        for evidence in result.evidence:
            key = (evidence.metadata.document_id, evidence.metadata.version)
            source = by_revision.get(key)
            if source is None:
                raise CitationError(CitationFailure.SOURCE_UNAVAILABLE)
            if key not in verified:
                verify_source(source)
                verified.add(key)
            catalog.append(_passage_citation(evidence, source))
        return tuple(catalog)
    except ValidationError:
        raise CitationError(CitationFailure.INVALID_INPUT) from None
    except UnicodeError:
        raise CitationError(CitationFailure.SOURCE_MISMATCH) from None


def assemble_citations(
    claims: tuple[ClaimDraft, ...],
    request: RetrievalRequest,
    result: RetrievalResult,
    sources: tuple[MarkdownDocument, ...],
) -> CitationReport:
    """Resolve model/caller references using trusted evidence and loaded sources."""
    try:
        claims = tuple(ClaimDraft.model_validate(claim) for claim in claims)
        request = RetrievalRequest.model_validate(request)
        result = RetrievalResult.model_validate(result)
        sources = tuple(MarkdownDocument.model_validate(source) for source in sources)
        if len({claim.claim_id for claim in claims}) != len(claims):
            raise CitationError(CitationFailure.INVALID_INPUT)
        _check_eligibility(request, result)
        by_revision = {
            (source.metadata.document_id, source.metadata.version): source
            for source in sources
        }
        if len(by_revision) != len(sources):
            raise CitationError(CitationFailure.INVALID_INPUT)
        by_chunk = {item.chunk_id: item for item in result.evidence}
        verified_sources: set[tuple[str, str]] = set()
        citations: dict[UUID, Citation] = {}
        assembled: list[CitedClaim] = []
        for claim in claims:
            attributed: list[AttributedCitation] = []
            for reference in claim.references:
                evidence = by_chunk.get(reference.chunk_id)
                if evidence is None:
                    raise CitationError(CitationFailure.UNKNOWN_REFERENCE)
                if reference.chunk_id not in citations:
                    key = (evidence.metadata.document_id, evidence.metadata.version)
                    source = by_revision.get(key)
                    if source is None:
                        raise CitationError(CitationFailure.SOURCE_UNAVAILABLE)
                    if key not in verified_sources:
                        verify_source(source)
                        verified_sources.add(key)
                    citations[reference.chunk_id] = _passage_citation(evidence, source)
                attributed.append(
                    AttributedCitation(
                        role=reference.role, citation=citations[reference.chunk_id]
                    )
                )
            assembled.append(CitedClaim(draft=claim, citations=tuple(attributed)))
        return CitationReport(claims=tuple(assembled))
    except ValidationError:
        raise CitationError(CitationFailure.INVALID_INPUT) from None
    except UnicodeError:
        raise CitationError(CitationFailure.SOURCE_MISMATCH) from None


def format_citation_location(citation: Citation) -> str:
    """Plain text source description; no generated link or customer projection."""
    citation = Citation.model_validate(citation)
    location = citation.passage.location
    revision = f"{citation.metadata.document_id}@{citation.metadata.version}"
    if location.kind == "markdown":
        heading = " > ".join(location.heading_path) or "Preamble"
        where = f"{heading}, lines {location.line_start}–{location.line_end}"
    else:
        where = f"page {location.page_number}"
    return f"{citation.metadata.title} ({revision}), {where}"
