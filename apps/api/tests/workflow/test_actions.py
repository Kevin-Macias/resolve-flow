"""Reviewed proposal validation, immutable revisions, and saved identity."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.extraction.schemas import Severity
from api.workflow.actions import (
    ActionRisk,
    CreateTicketArguments,
    ProposedAction,
    RiskLevel,
    propose_create_ticket,
    revise_create_ticket,
)
from api.workflow.checkpoints import checkpoint_serializer


def arguments() -> CreateTicketArguments:
    return CreateTicketArguments(
        issue_report_id=uuid4(),
        title="Pending payments",
        description="Customer reports two pending payments.",
        service_code=None,
        severity=None,
    )


def proposal() -> ProposedAction:
    return propose_create_ticket(
        arguments(),
        explanation="Support should investigate the reported impact.",
        expected_effect="Create one internal support ticket linked to this report.",
        risk=ActionRisk(level=RiskLevel.LOW, reason="Simulated ticket creation only."),
    )


def test_nullable_classification_and_normalized_text() -> None:
    action = proposal()
    assert action.tool == "create_ticket"
    assert action.version == 1
    assert action.arguments.service_code is None
    assert action.arguments.severity is None
    payload = action.arguments.model_dump()
    payload.update(title="  A title  ", severity="medium", service_code=" payments ")
    parsed = CreateTicketArguments.model_validate(payload)
    assert parsed.title == "A title"
    assert parsed.service_code == "payments"
    assert parsed.severity is Severity.MEDIUM


@pytest.mark.parametrize("field", ["title", "description", "service_code"])
def test_blank_argument_text_is_rejected(field: str) -> None:
    payload = arguments().model_dump()
    payload[field] = "   "
    with pytest.raises(ValidationError):
        CreateTicketArguments.model_validate(payload)


@pytest.mark.parametrize("field", ["issue_report_id", "service_code", "severity"])
def test_required_fields_cannot_be_omitted(field: str) -> None:
    payload = arguments().model_dump()
    del payload[field]
    with pytest.raises(ValidationError):
        CreateTicketArguments.model_validate(payload)


@pytest.mark.parametrize("extra", ["customer_account_id", "approved", "assignee"])
def test_scope_and_execution_fields_are_not_tool_arguments(extra: str) -> None:
    payload = arguments().model_dump()
    payload[extra] = "model-supplied"
    with pytest.raises(ValidationError):
        CreateTicketArguments.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tool", "delete_ticket"),
        ("version", 0),
        ("version", True),
        ("explanation", " "),
        ("expected_effect", " "),
    ],
)
def test_invalid_proposal_metadata_is_rejected(field: str, value: object) -> None:
    payload = proposal().model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        ProposedAction.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [{"level": "critical", "reason": "Reason"}, {"level": "low", "reason": " "}],
)
def test_risk_requires_an_allowed_level_and_nonempty_reason(
    payload: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        ActionRisk.model_validate(payload)


def test_proposal_and_nested_arguments_are_frozen() -> None:
    action = proposal()
    with pytest.raises(ValidationError):
        action.version = 2
    with pytest.raises(ValidationError):
        action.arguments.title = "Changed"
    with pytest.raises(ValidationError):
        action.risk.reason = "Changed"


def test_revision_changes_version_key_and_fingerprint_without_mutating_original() -> (
    None
):
    action = proposal()
    original_hash = action.fingerprint()
    payload = action.arguments.model_dump()
    payload["severity"] = Severity.MEDIUM
    revised = revise_create_ticket(
        action,
        CreateTicketArguments.model_validate(payload),
        explanation=action.explanation,
        expected_effect=action.expected_effect,
        risk=action.risk,
    )
    assert revised.action_id == action.action_id
    assert revised.version == 2
    assert revised.idempotency_key != action.idempotency_key
    assert revised.fingerprint() != original_hash
    assert action.version == 1
    assert action.arguments.severity is None
    assert action.fingerprint() == original_hash


def test_revision_cannot_move_to_another_report() -> None:
    action = proposal()
    with pytest.raises(ValueError, match="same issue report"):
        revise_create_ticket(
            action,
            arguments(),
            explanation=action.explanation,
            expected_effect=action.expected_effect,
            risk=action.risk,
        )


def test_saved_proposal_restores_exact_values_identity_and_fingerprint() -> None:
    action = proposal()
    serde = checkpoint_serializer()
    restored: object = serde.loads_typed(serde.dumps_typed(action))
    assert isinstance(restored, ProposedAction)
    assert isinstance(restored.arguments, CreateTicketArguments)
    assert isinstance(restored.risk, ActionRisk)
    assert restored == action
    assert restored.idempotency_key == action.idempotency_key
    assert restored.fingerprint() == action.fingerprint()


def test_fingerprint_covers_rationale_and_is_independent_of_key_order() -> None:
    action = proposal()
    payload = action.model_dump(mode="json")
    reordered = dict(reversed(list(payload.items())))
    assert (
        ProposedAction.model_validate(reordered).fingerprint() == action.fingerprint()
    )
    payload["explanation"] = "Updated rationale"
    assert ProposedAction.model_validate(payload).fingerprint() != action.fingerprint()


def test_unvalidated_model_copy_is_rejected_when_used_for_a_revision() -> None:
    action = proposal()
    unvalidated = action.arguments.model_copy(update={"title": ""})
    with pytest.raises(ValidationError):
        revise_create_ticket(
            action,
            unvalidated,
            explanation=action.explanation,
            expected_effect=action.expected_effect,
            risk=action.risk,
        )
