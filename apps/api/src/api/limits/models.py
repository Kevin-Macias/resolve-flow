"""Shared request windows contain hashed subjects, never credentials or bodies."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models import Base


class RequestWindow(Base):
    __tablename__ = "request_limit_windows"
    __table_args__ = (
        CheckConstraint("attempts > 0", name="attempts"),
        CheckConstraint("key_hash ~ '^[0-9a-f]{64}$'", name="key_hash"),
    )
    key_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    resets_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer)
