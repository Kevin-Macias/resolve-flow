"""Closed internal evidence responses, separate from customer intake."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from api.intake.schemas import Contract
from api.knowledge.citations import Citation, CitationReport


class AnalysisRequest(Contract):
    operation_id: UUID


class EvidencePassage(Contract):
    citation: Citation
    rank: int = Field(ge=1, le=5)
    score: float = Field(ge=-1, le=1, allow_inf_nan=False)
    score_metric: Literal["fixture", "cosine_similarity"]
    historical: bool


class SupportEvidence(Contract):
    version: Literal[1] = 1
    report_id: UUID
    analysis_id: UUID | None
    operation_id: UUID | None
    status: Literal["absent", "pending", "ready", "failed"]
    created_at: datetime | None
    provider_mode: Literal["offline", "live"] | None
    simulated: bool
    input_revision: int | None
    older_input: bool
    passages: tuple[EvidencePassage, ...] = Field(max_length=5)
    report: CitationReport

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        present = self.status != "absent"
        if any(
            (value is not None) != present
            for value in (
                self.analysis_id,
                self.operation_id,
                self.created_at,
                self.provider_mode,
            )
        ):
            raise ValueError("Inconsistent analysis identity")
        if self.simulated != (self.provider_mode == "offline"):
            raise ValueError("Inconsistent simulation label")
        if self.status != "ready" and (self.passages or self.report.claims):
            raise ValueError("Only ready analyses contain evidence")
        by_chunk = {item.citation.chunk_id: item.citation for item in self.passages}
        if len(by_chunk) != len(self.passages):
            raise ValueError("Duplicate passage")
        for index, item in enumerate(self.passages, 1):
            if item.rank != index or item.score_metric != (
                "fixture" if self.simulated else "cosine_similarity"
            ):
                raise ValueError("Inconsistent ranking")
        for claim in self.report.claims:
            if any(
                by_chunk.get(ref.citation.chunk_id) != ref.citation
                for ref in claim.citations
            ):
                raise ValueError("Claim citation is not in the evidence catalog")
        return self
