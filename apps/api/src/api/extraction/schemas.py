"""Validated output contract for issue-report extraction."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

type NonEmptyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: NonEmptyText
    service_code: NonEmptyText | None = Field(
        description="Tentative service code, or null when unknown."
    )
    severity: Severity | None = Field(
        description="Tentative severity, or null when impact is unknown."
    )
    confidence: Confidence
    reported_facts: list[NonEmptyText] = Field(
        description="Statements reported by the customer; not independently verified."
    )
    missing_data: list[NonEmptyText]
    contradictions: list[NonEmptyText] = Field(
        description="Conflicting customer statements that need clarification."
    )
    questions: list[NonEmptyText]
