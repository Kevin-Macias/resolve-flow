"""Typed clarification input and deterministic round policy."""

import json
from collections.abc import Sequence
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, ValidationError

from api.extraction.clarification import ClarificationDecision, ClarificationReason
from api.extraction.schemas import NonEmptyText

MAX_CLARIFICATION_ROUNDS = 2


class ClarificationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    round_number: int
    questions: tuple[str, ...]
    answers: tuple[str, ...]


class PendingClarification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pending_id: UUID
    round_number: int | None
    questions: tuple[str, ...]
    reasons: tuple[ClarificationReason, ...]
    mode: Literal["answer_or_continue", "continue_only"]
    cause: Literal["questions_available", "no_questions", "round_limit"]


class ClarificationReply(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pending_id: UUID
    action: Literal["answer", "continue_incomplete"]
    answers: tuple[NonEmptyText, ...] = ()


def prepare_clarification(
    decision: ClarificationDecision, completed_rounds: int
) -> PendingClarification:
    can_answer = completed_rounds < MAX_CLARIFICATION_ROUNDS and bool(
        decision.questions
    )
    return PendingClarification(
        pending_id=uuid4(),
        round_number=completed_rounds + 1 if can_answer else None,
        questions=decision.questions if can_answer else (),
        reasons=decision.reasons,
        mode="answer_or_continue" if can_answer else "continue_only",
        cause=(
            "round_limit"
            if completed_rounds >= MAX_CLARIFICATION_ROUNDS
            else "questions_available"
            if can_answer
            else "no_questions"
        ),
    )


def validate_reply(
    payload: object, pending: PendingClarification
) -> ClarificationReply | None:
    try:
        reply = ClarificationReply.model_validate(payload)
    except ValidationError:
        return None
    if reply.pending_id != pending.pending_id:
        return None
    if reply.action == "continue_incomplete":
        return reply if not reply.answers else None
    if pending.mode != "answer_or_continue":
        return None
    return reply if len(reply.answers) == len(pending.questions) else None


def extraction_input(report: str, turns: Sequence[ClarificationTurn]) -> str:
    if not turns:
        return report
    # JSON preserves boundaries between original observations and later answers.
    return json.dumps(
        {
            "original_report": report,
            "clarification_turns": [turn.model_dump(mode="json") for turn in turns],
        },
        ensure_ascii=False,
    )
