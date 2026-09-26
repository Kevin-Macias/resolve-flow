"""Deterministic policy for whether an extracted report needs clarification."""

from dataclasses import dataclass
from enum import StrEnum

from api.extraction.schemas import Confidence, ExtractionResult

MAX_QUESTIONS_PER_EXTRACTION = 2


class ClarificationReason(StrEnum):
    MISSING_DATA = "missing_data"
    CONTRADICTION = "contradiction"
    LOW_CONFIDENCE = "low_confidence"
    UNKNOWN_SERVICE = "unknown_service"
    UNKNOWN_SEVERITY = "unknown_severity"


@dataclass(frozen=True)
class ClarificationDecision:
    reasons: tuple[ClarificationReason, ...]
    questions: tuple[str, ...]

    @property
    def needs_clarification(self) -> bool:
        return bool(self.reasons)


def decide_clarification(extraction: ExtractionResult) -> ClarificationDecision:
    reasons: list[ClarificationReason] = []
    if extraction.missing_data:
        reasons.append(ClarificationReason.MISSING_DATA)
    if extraction.contradictions:
        reasons.append(ClarificationReason.CONTRADICTION)
    if extraction.confidence is Confidence.LOW:
        reasons.append(ClarificationReason.LOW_CONFIDENCE)
    if extraction.service_code is None:
        reasons.append(ClarificationReason.UNKNOWN_SERVICE)
    if extraction.severity is None:
        reasons.append(ClarificationReason.UNKNOWN_SEVERITY)

    if not reasons:
        return ClarificationDecision((), ())

    questions: list[str] = []
    seen: set[str] = set()
    for question in extraction.questions:
        key = question.casefold()
        if key not in seen:
            seen.add(key)
            questions.append(question)
            if len(questions) == MAX_QUESTIONS_PER_EXTRACTION:
                break
    return ClarificationDecision(tuple(reasons), tuple(questions))
