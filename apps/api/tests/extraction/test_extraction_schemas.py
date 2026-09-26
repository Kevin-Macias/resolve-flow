import pytest
from pydantic import ValidationError

from api.extraction.schemas import Confidence, ExtractionResult, Severity


def ambiguous_payment_report() -> dict[str, object]:
    return {
        "summary": "Payments sometimes remain pending after checkout",
        "service_code": "payments",
        "severity": None,
        "confidence": "low",
        "reported_facts": [
            "Customer reports pending payments after successful Stripe checkout"
        ],
        "missing_data": ["Number of affected payments", "When the issue began"],
        "contradictions": [],
        "questions": ["How many payments have remained pending, and since when?"],
    }


def test_ambiguous_report_keeps_unknown_severity() -> None:
    result = ExtractionResult.model_validate(ambiguous_payment_report())

    assert result.service_code == "payments"
    assert result.severity is None
    assert result.confidence is Confidence.LOW
    assert result.reported_facts == [
        "Customer reports pending payments after successful Stripe checkout"
    ]
    assert len(result.questions) == 1


def test_known_classification_and_empty_clarification_lists() -> None:
    payload = ambiguous_payment_report()
    payload.update(severity="high", confidence="medium", missing_data=[], questions=[])

    result = ExtractionResult.model_validate(payload)

    assert result.severity is Severity.HIGH
    assert result.confidence is Confidence.MEDIUM
    assert result.missing_data == []
    assert result.contradictions == []
    assert result.questions == []


def test_conflicting_customer_statements_are_kept_separately() -> None:
    payload = ambiguous_payment_report()
    payload["contradictions"] = [
        "Customer says no payment was charged but also says the card was charged"
    ]

    result = ExtractionResult.model_validate(payload)

    assert len(result.contradictions) == 1
    assert result.missing_data == [
        "Number of affected payments",
        "When the issue began",
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("summary", "   "),
        ("service_code", "   "),
        ("severity", "urgent"),
        ("confidence", "certain"),
        ("reported_facts", ["  "]),
        ("missing_data", ["  "]),
        ("contradictions", ["  "]),
        ("questions", ["  "]),
    ],
)
def test_invalid_extraction_values_are_rejected(field: str, value: object) -> None:
    payload = ambiguous_payment_report()
    payload[field] = value

    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "summary",
        "service_code",
        "severity",
        "confidence",
        "reported_facts",
        "missing_data",
        "contradictions",
        "questions",
    ],
)
def test_missing_required_field_is_rejected(field: str) -> None:
    payload = ambiguous_payment_report()
    del payload[field]

    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(payload)


def test_unexpected_field_is_rejected() -> None:
    payload = ambiguous_payment_report()
    payload["diagnosis"] = "Stripe is down"

    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(payload)
