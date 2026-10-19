from uuid import UUID as PythonUUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models import Base, Timestamps


class ModelCallAttempt(Timestamps, Base):
    __tablename__ = "model_call_attempts"
    __table_args__ = (
        CheckConstraint("scope_type IN ('intake','evidence')", name="scope_type"),
        CheckConstraint("attempt >= 1", name="attempt"),
        UniqueConstraint("call_id", "attempt"),
        Index("ix_model_call_attempts_report_id", "report_id"),
    )
    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    report_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issue_reports.id", ondelete="RESTRICT")
    )
    customer_account_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_accounts.id", ondelete="RESTRICT")
    )
    scope_type: Mapped[str] = mapped_column(Text)
    scope_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True))
    operation_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True))
    call_id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True))
    attempt: Mapped[int] = mapped_column(Integer)
    record: Mapped[dict[str, object]] = mapped_column(JSONB)
