"""Permanent credentials, single-use invitations, and revocable opaque sessions."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models import Base, Timestamps


class AuthCredential(Timestamps, Base):
    __tablename__ = "auth_credentials"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Timestamps, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash"),
        CheckConstraint(
            "(user_type = 'customer' AND customer_account_id IS NOT NULL) OR (user_type = 'support' AND customer_account_id IS NULL)",
            name="user_type_account",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth_credentials.user_id", ondelete="RESTRICT")
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    user_type: Mapped[str] = mapped_column(Text)
    customer_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customer_accounts.id", ondelete="RESTRICT")
    )
    is_admin: Mapped[bool] = mapped_column(Boolean)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthInvitation(Timestamps, Base):
    __tablename__ = "auth_invitations"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash"),
        CheckConstraint(
            "(user_type = 'customer' AND customer_account_id IS NOT NULL) OR (user_type = 'support' AND customer_account_id IS NULL)",
            name="user_type_account",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(Text)
    user_type: Mapped[str] = mapped_column(Text)
    customer_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customer_accounts.id", ondelete="RESTRICT")
    )
    support_account_ids: Mapped[list[str]] = mapped_column(JSONB)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("auth_credentials.user_id", ondelete="RESTRICT")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportAccountGrant(Timestamps, Base):
    __tablename__ = "support_account_grants"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    customer_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("customer_accounts.id", ondelete="RESTRICT"), primary_key=True
    )


class AuthAttemptWindow(Base):
    __tablename__ = "auth_attempt_windows"
    __table_args__ = (CheckConstraint("attempts > 0", name="attempts"),)
    key_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer)
