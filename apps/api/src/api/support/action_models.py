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
