"""PostgreSQL concurrency and real HTTP rejection before handler work."""

import asyncio
import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient, Response
from psycopg import AsyncConnection, sql
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.models import Base
from api.identity import service
from api.limits.models import RequestWindow
from api.limits.rate import Budget, RateLimiter, RatePolicy
from api.main import create_app
from api.workflow.checkpoints import postgres_connection_url


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def counters() -> AsyncGenerator[
    tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]]
]:
    raw = os.getenv("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set TEST_DATABASE_URL for shared request-limit tests")
    url = postgres_connection_url(raw)
    schema = f"rf_limits_{uuid4().hex}"
    async with await AsyncConnection.connect(url, autocommit=True) as connection:
        await connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
        )
    engines = [
        create_async_engine(
            url.replace("postgresql://", "postgresql+psycopg://"),
            connect_args={"options": f"-csearch_path={schema},public"},
        )
        for _ in range(2)
    ]
    try:
        async with engines[0].begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(
                    conn, tables=[Base.metadata.tables["request_limit_windows"]]
                )
            )
        yield (
            async_sessionmaker(engines[0], expire_on_commit=False),
            async_sessionmaker(engines[1], expire_on_commit=False),
        )
    finally:
        for engine in engines:
            await engine.dispose()
        async with await AsyncConnection.connect(url, autocommit=True) as connection:
            await connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.mark.anyio
async def test_atomic_limit_is_shared_by_independent_workers_and_new_instances(
    counters: tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]],
) -> None:
    budget = Budget("operation", "private-user-or-token", 5)

    async def attempt(i: int) -> int:
        try:
            await RateLimiter(counters[i % 2]).reserve((budget,))
            return 200
        except HTTPException as error:
            assert error.status_code == 429
            assert 1 <= int((error.headers or {})["Retry-After"]) <= 60
            return error.status_code

    statuses = await asyncio.gather(*(attempt(i) for i in range(40)))
    assert statuses.count(200) == 5 and statuses.count(429) == 35
    assert await attempt(1) == 429
    async with counters[0]() as session:
        rows = (await session.scalars(select(RequestWindow))).all()
        assert len(rows) == 1 and rows[0].attempts == 5
        assert rows[0].key_hash == budget.key and "private" not in rows[0].key_hash


@pytest.mark.anyio
async def test_expiry_resets_and_other_subjects_and_policies_are_independent(
    counters: tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]],
) -> None:
    limiter = RateLimiter(counters[0])
    first = Budget("user", "a", 1)
    await limiter.reserve((first,))
    await limiter.reserve((Budget("user", "b", 1),))
    await limiter.reserve((Budget("other", "a", 1),))
    with pytest.raises(HTTPException) as denied:
        await limiter.reserve((first,))
    assert denied.value.status_code == 429
    async with counters[0]() as session:
        await session.execute(
            update(RequestWindow)
            .where(RequestWindow.key_hash == first.key)
            .values(resets_at=func.clock_timestamp() - timedelta(seconds=1))
        )
        await session.commit()
    await RateLimiter(counters[1]).reserve((first,))
    async with counters[0]() as session:
        row = await session.get(RequestWindow, first.key)
        assert row is not None and row.attempts == 1


@pytest.mark.anyio
async def test_multi_budget_rejection_rolls_back_other_reservations(
    counters: tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]],
) -> None:
    limiter = RateLimiter(counters[0])
    hard = Budget("hard", "a", 1)
    soft = next(
        Budget("soft", str(i), 10)
        for i in range(100)
        if Budget("soft", str(i), 10).key < hard.key
    )
    await limiter.reserve((hard,))
    with pytest.raises(HTTPException):
        await limiter.reserve((soft, hard))
    async with counters[0]() as session:
        assert await session.get(RequestWindow, soft.key) is None
        row = await session.get(RequestWindow, hard.key)
        assert row is not None and row.attempts == 1


@pytest.mark.anyio
async def test_cleanup_is_bounded_and_keeps_recent_windows(
    counters: tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]],
) -> None:
    now = datetime.now(UTC)
    async with counters[0]() as session:
        session.add_all(
            RequestWindow(
                key_hash=Budget("stale", str(i), 1).key,
                attempts=1,
                resets_at=now - timedelta(days=2),
            )
            for i in range(105)
        )
        session.add(
            RequestWindow(
                key_hash=Budget("recent", "a", 1).key,
                attempts=1,
                resets_at=now - timedelta(hours=1),
            )
        )
        await session.commit()
    await RateLimiter(counters[0]).reserve((Budget("new", "a", 1),))
    async with counters[0]() as session:
        assert (
            await session.scalar(select(func.count()).select_from(RequestWindow)) == 7
        )
        assert (
            await session.get(RequestWindow, Budget("recent", "a", 1).key) is not None
        )


@pytest.mark.anyio
async def test_auth_peer_limit_cannot_be_bypassed_by_email_or_forwarded_headers(
    counters: tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = AsyncMock(side_effect=HTTPException(401, "Invalid credentials"))
    monkeypatch.setattr(service, "login", handler)
    apps = [create_app(), create_app()]
    for app in apps:
        app.state.session_factory = counters[0]
        app.state.rate_policy = RatePolicy(authentication=2)
    result: Response | None = None
    for index in range(3):
        async with AsyncClient(
            transport=ASGITransport(app=apps[index % 2]), base_url="http://test"
        ) as client:
            result = await client.post(
                "/auth/login",
                json={"email": f"user{index}@example.com", "password": "invalid"},
                headers={
                    "X-Forwarded-For": f"192.0.2.{index}",
                    "Origin": "http://localhost:3000",
                },
            )
        assert result.status_code == (401 if index < 2 else 429)
    assert result is not None
    assert handler.await_count == 2
    assert result.json()["error"]["code"] == "rate_limited"
    assert int(result.headers["retry-after"]) > 0
    assert "Retry-After" in result.headers["access-control-expose-headers"]
    assert result.headers["x-request-id"]
    async with AsyncClient(
        transport=ASGITransport(app=apps[0], client=("192.0.2.20", 123)),
        base_url="http://test",
    ) as client:
        result = await client.post(
            "/auth/login", json={"email": "other@example.com", "password": "invalid"}
        )
    assert result.status_code == 401 and handler.await_count == 3


@pytest.mark.anyio
async def test_peer_limit_precedes_json_parsing_and_health_and_preflight_are_exempt(
    counters: tuple[async_sessionmaker[AsyncSession], async_sessionmaker[AsyncSession]],
) -> None:
    app = create_app()
    app.state.session_factory = counters[0]
    app.state.rate_policy = RatePolicy(peer=1)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/auth/login", content=b"invalid json")
        assert first.status_code == 422
        second = await client.post("/auth/invitations/redeem", content=b"invalid json")
        assert second.status_code == 429
        assert (await client.get("/health")).status_code == 200
        preflight = await client.options(
            "/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.status_code == 200


@pytest.mark.anyio
async def test_database_failure_never_dispatches_or_exposes_connection_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        "postgresql+psycopg://secret:secret@127.0.0.1:1/private"
    )
    app = create_app()
    app.state.session_factory = async_sessionmaker(engine)
    handler = AsyncMock()
    monkeypatch.setattr(service, "login", handler)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            result = await client.post(
                "/auth/login",
                json={"email": "person@example.com", "password": "invalid"},
            )
        assert result.status_code == 503 and handler.await_count == 0
        assert "secret" not in result.text and "private" not in result.text
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "configuration",
    [
        '{"peer":0}',
        '{"peer":-1}',
        '{"peer":true}',
        '{"peer":10001}',
        '{"unknown":1}',
    ],
)
def test_invalid_limit_configuration_prevents_startup(
    monkeypatch: pytest.MonkeyPatch, configuration: str
) -> None:
    monkeypatch.setenv("REQUEST_LIMITS", configuration)
    with pytest.raises(ValidationError):
        create_app()
