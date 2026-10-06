"""Immutable application-owned proposals; this module executes no tools."""

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from api.extraction.schemas import NonEmptyText, Severity


class ImmutableContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always"
    )


class CreateTicketArguments(ImmutableContract):
    issue_report_id: UUID
    title: NonEmptyText
    description: NonEmptyText
    service_code: NonEmptyText | None
    severity: Severity | None


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionRisk(ImmutableContract):
    level: RiskLevel
    reason: NonEmptyText


class ProposedAction(ImmutableContract):
    action_id: UUID
    version: Annotated[int, Field(strict=True, ge=1)]
    idempotency_key: UUID
    tool: Literal["create_ticket"] = "create_ticket"
    arguments: CreateTicketArguments
    explanation: NonEmptyText
    expected_effect: NonEmptyText
    risk: ActionRisk

    def fingerprint(self) -> str:
        """Bind later review to the entire normalized snapshot, not only its ID."""
        payload = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def propose_create_ticket(
    arguments: CreateTicketArguments,
    *,
    explanation: str,
    expected_effect: str,
    risk: ActionRisk,
) -> ProposedAction:
    return ProposedAction(
        action_id=uuid4(),
        version=1,
        idempotency_key=uuid4(),
        arguments=arguments,
        explanation=explanation,
        expected_effect=expected_effect,
        risk=risk,
    )


def revise_create_ticket(
    previous: ProposedAction,
    arguments: CreateTicketArguments,
    *,
    explanation: str,
    expected_effect: str,
    risk: ActionRisk,
) -> ProposedAction:
    previous = ProposedAction.model_validate(previous)
    arguments = CreateTicketArguments.model_validate(arguments)
    if arguments.issue_report_id != previous.arguments.issue_report_id:
        raise ValueError("A revision must belong to the same issue report")
    return ProposedAction(
        action_id=previous.action_id,
        version=previous.version + 1,
        idempotency_key=uuid4(),
        arguments=arguments,
        explanation=explanation,
        expected_effect=expected_effect,
        risk=risk,
    )
