"""Clarification decisions are bounded and explain why questions are needed."""

import pytest

from api.extraction.clarification import (
    ClarificationReason,
    decide_clarification,
)
from api.extraction.schemas import ExtractionResult


def extraction_with(**changes: object) -> ExtractionResult:
    payload: dict[str, object] = {
        "summary": "Invoice submission fails",
        "service_code": "invoicing",
        "severity": "medium",
        "confidence": "high",
        "reported_facts": ["Customer reports invoice submission fails"],
        "missing_data": [],
        "contradictions": [],
        "questions": [],
    }
    payload.update(changes)
    return ExtractionResult.model_validate(payload)


def test_complete_report_needs_no_clarification() -> None:
    decision = decide_clarification(extraction_with(questions=["Unneeded question?"]))

    assert not decision.needs_clarification
    assert decision.reasons == ()
    assert decision.questions == ()


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"missing_data": ["Start time"]}, ClarificationReason.MISSING_DATA),
        (
            {"contradictions": ["Customer reports both a charge and no charge"]},
            ClarificationReason.CONTRADICTION,
        ),
        ({"confidence": "low"}, ClarificationReason.LOW_CONFIDENCE),
        ({"service_code": None}, ClarificationReason.UNKNOWN_SERVICE),
        ({"severity": None}, ClarificationReason.UNKNOWN_SEVERITY),
    ],
)
def test_each_gap_is_identified(
    change: dict[str, object], reason: ClarificationReason
) -> None:
    decision = decide_clarification(extraction_with(**change))

    assert decision.needs_clarification
    assert decision.reasons == (reason,)


def test_questions_are_deduplicated_and_capped_at_two() -> None:
    decision = decide_clarification(
        extraction_with(
            contradictions=["Report says both charged and not charged"],
            missing_data=["Start time"],
            questions=[
                "When did this begin?",
                "when did this begin?",
                "Was the card charged?",
                "Which browser did you use?",
            ],
        )
    )

    assert decision.reasons == (
        ClarificationReason.MISSING_DATA,
        ClarificationReason.CONTRADICTION,
    )
    assert decision.questions == ("When did this begin?", "Was the card charged?")


def test_missing_question_does_not_create_an_unsupported_one() -> None:
    decision = decide_clarification(extraction_with(severity=None))

    assert decision.needs_clarification
    assert decision.questions == ()
