"""Durable, report-scoped preliminary support analysis operations."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models import Base, Timestamps


class EvidenceAnalysis(Timestamps, Base):
    __tablename__ = "evidence_analyses"
    accounting_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (
        UniqueConstraint("report_id", "operation_id"),
        CheckConstraint("status IN ('pending', 'ready', 'failed')", name="status"),
        CheckConstraint("input_hash ~ '^[0-9a-f]{64}$'", name="input_hash"),
        CheckConstraint("provider_mode IN ('offline', 'live')", name="provider_mode"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("issue_reports.id", ondelete="RESTRICT"), index=True
    )
    customer_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("customer_accounts.id", ondelete="RESTRICT")
    )
    operation_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(Text)
    provider_mode: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(Text)
    input_record: Mapped[dict[str, object]] = mapped_column(JSONB)
    result_record: Mapped[dict[str, object] | None] = mapped_column(JSONB)
