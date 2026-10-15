from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models import Base, Timestamps


class IntakeRun(Timestamps, Base):
    __tablename__ = "intake_runs"
    __table_args__ = (
        CheckConstraint("revision BETWEEN 1 AND 9007199254740991", name="revision"),
        CheckConstraint("provider_mode IN ('offline', 'live')", name="provider_mode"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("issue_reports.id", ondelete="RESTRICT"), unique=True
    )
    customer_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("customer_accounts.id", ondelete="RESTRICT")
    )
    initiated_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    provider_mode: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(BigInteger)
    public_view: Mapped[dict[str, object]] = mapped_column(JSONB)
    pending_operation_id: Mapped[UUID | None]


class IntakeOperation(Timestamps, Base):
    __tablename__ = "intake_operations"
    __table_args__ = (
        CheckConstraint("kind IN ('start', 'clarification')", name="kind"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="payload_hash"),
    )
    # UUID reuse is scoped to a run, so clients cannot probe another run's keys.
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("intake_runs.id", ondelete="RESTRICT"), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    payload_hash: Mapped[str] = mapped_column(Text)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
