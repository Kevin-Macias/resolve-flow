from collections.abc import AsyncGenerator
from typing import Annotated
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from starlette.requests import Request

from api.db.session import get_session
from api.main import create_app
from api.system.service import DatabaseNotConfiguredError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_lifespan_keeps_health_available_without_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app()

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/health")).status_code == 200
            assert app.state.session_factory is None


@pytest.mark.anyio
async def test_session_requires_database_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app()

    async with app.router.lifespan_context(app):
        request = Request({"type": "http", "app": app})
        with pytest.raises(DatabaseNotConfiguredError):
            await anext(get_session(request))


@pytest.mark.anyio
async def test_lifespan_reuses_factory_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost/test")
    app = create_app()

    async with app.router.lifespan_context(app):
        factory = app.state.session_factory
        assert factory is not None
        assert factory.kw["expire_on_commit"] is False
        assert factory.kw["bind"].url.drivername == "postgresql+psycopg"
        dispose = AsyncMock(wraps=factory.kw["bind"].dispose)
        monkeypatch.setattr(AsyncEngine, "dispose", dispose)

        request = Request({"type": "http", "app": app})
        first = get_session(request)
        second = get_session(request)
        first_session = await anext(first)
        second_session = await anext(second)
        assert first_session is not second_session
        assert app.state.session_factory is factory
        await first_session.begin()
        assert first_session.in_transaction()
        await first.aclose()
        await second.aclose()
        assert not first_session.in_transaction()

    assert app.state.session_factory is None
    dispose.assert_awaited_once()


@pytest.mark.anyio
async def test_fastapi_can_override_session_dependency() -> None:
    app: FastAPI = create_app()
    supplied_session = AsyncSession()

    async def override_session() -> AsyncGenerator[AsyncSession]:
        yield supplied_session

    async def probe(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> dict[str, bool]:
        return {"overridden": session is supplied_session}

    app.get("/session-probe")(probe)
    app.dependency_overrides[get_session] = override_session

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/session-probe")

    assert response.status_code == 200
    assert response.json() == {"overridden": True}
    await supplied_session.close()
