from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.errors import ErrorResponse
from api.system.service import (
    DatabaseNotConfiguredError,
    DatabaseUnavailableError,
    SystemService,
)

router = APIRouter(tags=["system"])


def get_system_service() -> SystemService:
    return SystemService()


SystemServiceDependency = Annotated[SystemService, Depends(get_system_service)]


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "resolve-flow-api",
        "name": "ResolveFlow API",
    }


@router.get("/ready", responses={503: {"model": ErrorResponse}})
async def readiness(service: SystemServiceDependency) -> dict[str, str]:
    try:
        await service.check_database_readiness()
    except DatabaseNotConfiguredError as error:
        raise HTTPException(
            status_code=503, detail="Database configuration is missing"
        ) from error
    except DatabaseUnavailableError as error:
        raise HTTPException(
            status_code=503, detail="Database is unavailable"
        ) from error

    return {
        "status": "ready",
        "database": "connected",
    }
