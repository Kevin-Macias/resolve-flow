"""Application-owned retrieval contracts and checked adapter boundary."""

from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import Field, ValidationError, model_validator

from api.knowledge.metadata import (
    AccessClass,
    DocumentMetadata,
    DocumentStatus,
    KnowledgeContract,
    PassageLocation,
    PositiveInt,
    Text,
)


class DocumentRevision(KnowledgeContract):
    document_id: Text
    version: Text


class RetrievalScope(KnowledgeContract):
    """Permissions already established by trusted application code."""

    allow_internal: Annotated[bool, Field(strict=True)] = False
    customer_account_ids: frozenset[UUID] = frozenset()


class RetrievalRequest(KnowledgeContract):
    query: Text
    scope: RetrievalScope
    active_revisions: tuple[DocumentRevision, ...]
    service_code: Text | None = None
    top_k: Annotated[int, Field(strict=True, ge=1, le=20)] = 5

    @model_validator(mode="after")
    def validate_active_revisions(self) -> Self:
        identities = [revision.document_id for revision in self.active_revisions]
        if len(identities) != len(set(identities)):
            raise ValueError("Select at most one active revision per document")
        return self


class EvidenceCandidate(KnowledgeContract):
    chunk_id: UUID
    text: Annotated[str, Field(strict=True, min_length=1)]
    metadata: DocumentMetadata
    passage: PassageLocation
    score: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]
    score_metric: Literal["cosine_similarity", "fixture"]

    @model_validator(mode="after")
    def validate_passage(self) -> Self:
        if not self.text.strip():
            raise ValueError("Evidence text cannot be blank")
        if (self.metadata.document_id, self.metadata.version) != (
            self.passage.document_id,
            self.passage.version,
        ):
            raise ValueError("Evidence metadata and passage revision must agree")
        return self


class RankedEvidence(EvidenceCandidate):
    rank: PositiveInt


class RetrievalResult(KnowledgeContract):
    evidence: tuple[RankedEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_ranking(self) -> Self:
        identities = [item.chunk_id for item in self.evidence]
        if len(identities) != len(set(identities)):
            raise ValueError("Retrieved chunk identities must be unique")
        metrics = {item.score_metric for item in self.evidence}
        if len(metrics) > 1:
            raise ValueError("Retrieved scores must use the same metric")
        for expected, item in enumerate(self.evidence, start=1):
            if item.rank != expected:
                raise ValueError("Evidence ranks must be contiguous starting at one")
        keys = [(-item.score, str(item.chunk_id)) for item in self.evidence]
        if keys != sorted(keys):
            raise ValueError("Evidence must be ordered by score and chunk identity")
        return self


class RetrievalFailure(StrEnum):
    INVALID_INPUT = "invalid_input"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"


class RetrievalError(Exception):
    """Fixed public messages avoid exposing adapter or source details."""

    def __init__(self, reason: RetrievalFailure) -> None:
        self.reason = reason
        super().__init__(f"Retrieval failed: {reason.value}")


class Retriever(Protocol):
    async def search(self, request: RetrievalRequest) -> RetrievalResult: ...


def is_eligible(metadata: DocumentMetadata, request: RetrievalRequest) -> bool:
    active = any(
        revision.document_id == metadata.document_id
        and revision.version == metadata.version
        for revision in request.active_revisions
    )
    if not active or metadata.status != DocumentStatus.CURRENT:
        return False
    if (
        request.service_code is not None
        and metadata.service_code != request.service_code
    ):
        return False
    match metadata.access_class:
        case AccessClass.PUBLIC:
            return True
        case AccessClass.INTERNAL:
            return request.scope.allow_internal
        case AccessClass.CUSTOMER_ACCOUNT:
            return metadata.customer_account_id in request.scope.customer_account_ids


class RetrievalService:
    """Checks an adapter's output before application consumers receive evidence."""

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    async def search(self, request: RetrievalRequest) -> RetrievalResult:
        # Invalid caller input remains a validation error, not a search failure.
        request = RetrievalRequest.model_validate(request)
        try:
            response = await self._retriever.search(request)
            result = RetrievalResult.model_validate(response)
            if len(result.evidence) > request.top_k or any(
                not is_eligible(item.metadata, request) for item in result.evidence
            ):
                raise RetrievalError(RetrievalFailure.INVALID_RESPONSE)
            return result
        except RetrievalError as error:
            raise RetrievalError(error.reason) from None
        except ValidationError:
            raise RetrievalError(RetrievalFailure.INVALID_RESPONSE) from None
        except TimeoutError:
            raise RetrievalError(RetrievalFailure.TIMEOUT) from None
        except Exception:
            raise RetrievalError(RetrievalFailure.UNAVAILABLE) from None
