import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from api.main import create_app
from api.system.router import get_system_service
from api.system.service import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    SystemService,
)


class ReadySystemService(SystemService):
    async def check_database_readiness(self) -> None:
        return None


class NotConfiguredSystemService(SystemService):
    async def check_database_readiness(self) -> None:
        raise DatabaseNotConfiguredError()


class UnavailableSystemService(SystemService):
    async def check_database_readiness(self) -> None:
        raise DatabaseUnavailableError()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def create_test_app(system_service: SystemService | None = None) -> FastAPI:
    application = create_app()

    if system_service is not None:

        async def override_system_service() -> SystemService:
            return system_service

        application.dependency_overrides[get_system_service] = override_system_service

    return application


async def get(application: FastAPI, path: str) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        return await client.get(path)


@pytest.mark.anyio
async def test_factory_app_exposes_health() -> None:
    response = await get(create_test_app(), "/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "resolve-flow-api",
        "name": "ResolveFlow API",
    }


@pytest.mark.anyio
async def test_readiness_succeeds_when_database_is_ready() -> None:
    response = await get(create_test_app(ReadySystemService()), "/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


@pytest.mark.anyio
async def test_readiness_rejects_missing_database_configuration() -> None:
    response = await get(create_test_app(NotConfiguredSystemService()), "/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database configuration is missing"}


@pytest.mark.anyio
async def test_readiness_rejects_unavailable_database() -> None:
    response = await get(create_test_app(UnavailableSystemService()), "/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}
