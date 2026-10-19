"""Report/run bindings and replayable proposal preparation operations."""

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models import Base, Timestamps


class SupportActionRun(Timestamps, Base):
    __tablename__ = "support_action_runs"
    __table_args__ = (
        CheckConstraint("input_hash ~ '^[0-9a-f]{64}$'", name="input_hash"),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("intake_runs.id", ondelete="RESTRICT"), primary_key=True
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("issue_reports.id", ondelete="RESTRICT"), unique=True
    )
    customer_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("customer_accounts.id", ondelete="RESTRICT")
    )
    proposal: Mapped[dict[str, object]] = mapped_column(JSONB)
    input_record: Mapped[dict[str, object]] = mapped_column(JSONB)
    input_hash: Mapped[str] = mapped_column(Text)
    preparing: Mapped[bool] = mapped_column(Boolean)
    operation_id: Mapped[UUID]


class ProposalPreparation(Timestamps, Base):
    __tablename__ = "proposal_preparations"
    __table_args__ = (
        UniqueConstraint("run_id", "proposal_fingerprint"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="payload_hash"),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("support_action_runs.run_id", ondelete="RESTRICT"), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    payload_hash: Mapped[str] = mapped_column(Text)
    proposal_fingerprint: Mapped[str] = mapped_column(Text)
    completed: Mapped[bool] = mapped_column(Boolean)


class ExecutionOperation(Timestamps, Base):
    """Application intent, committed before asking the simulated destination."""

    __tablename__ = "execution_operations"
    __table_args__ = (
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
    )
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("support_action_runs.run_id", ondelete="RESTRICT"), unique=True
    )
    fingerprint: Mapped[str] = mapped_column(Text)
    proposal: Mapped[dict[str, object]] = mapped_column(JSONB)
    approval: Mapped[dict[str, object]] = mapped_column(JSONB)
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True))


class SimulatedTicketEffect(Timestamps, Base):
    """Destination-owned simulated effect and receipt in one committed row.

    No FK to the caller's operation ledger: this models a separate destination
    that knows only the operation key and the approved request it received.
    """

    __tablename__ = "simulated_ticket_effects"
    __table_args__ = (
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
    )
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(Text)
    ticket_id: Mapped[UUID] = mapped_column(unique=True)
    result: Mapped[dict[str, object]] = mapped_column(JSONB)
