"""Atomic fixed windows shared by API workers, with bounded cleanup."""

import asyncio
import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.limits.models import RequestWindow


class RatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    peer: int = Field(default=120, ge=1, le=10000)
    authentication: int = Field(default=20, ge=1, le=10000)
    user: int = Field(default=120, ge=1, le=10000)
    mutations: int = Field(default=30, ge=1, le=10000)
    model_operations: int = Field(default=10, ge=1, le=10000)
    global_model_operations: int = Field(default=60, ge=1, le=10000)


@dataclass(frozen=True)
class Budget:
    policy: str
    subject: str
    limit: int

    @property
    def key(self) -> str:
        return hashlib.sha256(
            f"resolveflow:request-limit:v1:{self.policy}:{self.subject}".encode()
        ).hexdigest()


class RateLimiter:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def reserve(self, budgets: tuple[Budget, ...]) -> None:
        """Commit all reservations together; a denied request runs no endpoint work."""
        try:
            async with asyncio.timeout(5), self.sessions() as session:
                await session.execute(text("SET LOCAL lock_timeout = '3s'"))
                await session.execute(text("SET LOCAL statement_timeout = '3s'"))
                now = await session.scalar(select(func.clock_timestamp()))
                assert isinstance(now, datetime)
                # Old inactive subjects are removed in small batches. SKIP LOCKED
                # avoids waiting on another worker's active counter or cleanup.
                stale = (
                    select(RequestWindow.key_hash)
                    .where(RequestWindow.resets_at < now - timedelta(days=1))
                    .order_by(RequestWindow.resets_at, RequestWindow.key_hash)
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
                await session.execute(
                    delete(RequestWindow).where(RequestWindow.key_hash.in_(stale))
                )
                # Stable lock ordering avoids deadlocks across overlapping budgets.
                for budget in sorted(budgets, key=lambda value: value.key):
                    expired = RequestWindow.resets_at <= now
                    reset = now + timedelta(seconds=60)
                    row = (
                        await session.execute(
                            insert(RequestWindow)
                            .values(key_hash=budget.key, resets_at=reset, attempts=1)
                            .on_conflict_do_update(
                                index_elements=["key_hash"],
                                set_={
                                    "resets_at": case(
                                        (expired, reset), else_=RequestWindow.resets_at
                                    ),
                                    "attempts": case(
                                        (expired, 1), else_=RequestWindow.attempts + 1
                                    ),
                                },
                                where=expired | (RequestWindow.attempts < budget.limit),
                            )
                            .returning(RequestWindow.attempts)
                        )
                    ).scalar_one_or_none()
                    if row is None:
                        resets_at = await session.scalar(
                            select(RequestWindow.resets_at).where(
                                RequestWindow.key_hash == budget.key
                            )
                        )
                        assert resets_at is not None
                        retry = max(1, math.ceil((resets_at - now).total_seconds()))
                        raise HTTPException(
                            429,
                            "Too many requests",
                            headers={"Retry-After": str(retry)},
                        )
                await session.commit()
        except (SQLAlchemyError, TimeoutError):
            raise HTTPException(503, "Request limits unavailable") from None
