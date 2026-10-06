"""Application-owned approval input and decisions bound to exact proposals."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, ValidationError

from api.identity.context import RequestContext
from api.workflow.actions import ImmutableContract, ProposedAction


class ApprovalChoice(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalReply(ImmutableContract):
    action_id: UUID
    version: Annotated[int, Field(strict=True, ge=1)]
    fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    decision: ApprovalChoice


class ApprovalDecision(ApprovalReply):
    actor_id: UUID
    decided_at: AwareDatetime

    def permits(self, proposal: ProposedAction) -> bool:
        proposal = ProposedAction.model_validate(proposal)
        return self.decision is ApprovalChoice.APPROVE and matches(self, proposal)


def matches(reply: ApprovalReply, proposal: ProposedAction) -> bool:
    return (
        reply.action_id == proposal.action_id
        and reply.version == proposal.version
        and reply.fingerprint == proposal.fingerprint()
    )


def validate_approval_reply(
    payload: object, proposal: ProposedAction
) -> ApprovalReply | None:
    try:
        reply = ApprovalReply.model_validate(payload)
    except ValidationError:
        return None
    return reply if matches(reply, proposal) else None


def record_approval(
    reply: ApprovalReply, proposal: ProposedAction, context: RequestContext
) -> ApprovalDecision:
    if context.user_type != "support":
        raise PermissionError("Only authorized support can decide an action")
    reply = ApprovalReply.model_validate(reply)
    proposal = ProposedAction.model_validate(proposal)
    if not matches(reply, proposal):
        raise ValueError("Approval must match the current proposal")
    return ApprovalDecision(
        **reply.model_dump(), actor_id=context.user_id, decided_at=datetime.now(UTC)
    )
