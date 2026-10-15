from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from api.streaming.transport import MAX_REVISION, CustomerSnapshot

Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
Revision = Annotated[int, Field(strict=True, ge=1, le=MAX_REVISION)]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_serialization_defaults_required=True
    )


class EmptyStart(Contract):
    pass


class ClarificationRequest(Contract):
    operation_id: UUID
    expected_revision: Revision
    pending_id: UUID
    action: Literal["answer", "continue_incomplete"]
    answers: tuple[Text, ...] = Field(default=(), max_length=2)

    def reply(self) -> dict[str, object]:
        return self.model_dump(
            mode="json", exclude={"operation_id", "expected_revision"}
        )


class RecoveryRequest(Contract):
    expected_revision: Revision


class CustomerPause(Contract):
    pending_id: UUID
    round_number: int | None
    mode: Literal["answer_or_continue", "continue_only"]
    cause: Literal["questions_available", "no_questions", "round_limit"]
    questions: tuple[Text, ...] = Field(max_length=2)


class CustomerTurn(Contract):
    round_number: Annotated[int, Field(ge=1, le=2)]
    questions: tuple[Text, ...] = Field(max_length=2)
    answers: tuple[Text, ...] = Field(max_length=2)


class CustomerRun(Contract):
    version: Literal[1] = 1
    run_id: UUID
    report_id: UUID
    revision: Revision
    status: Literal["processing", "needs_clarification", "needs_confirmation", "failed"]
    provider_mode: Literal["offline", "live"]
    simulated: bool
    message: Text
    operation_pending: bool
    pending: CustomerPause | None
    turns: tuple[CustomerTurn, ...] = Field(max_length=2)
    incomplete: bool
    snapshot: CustomerSnapshot
