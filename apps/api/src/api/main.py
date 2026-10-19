import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db.session import database_lifespan
from api.errors import ErrorResponse, install_error_handlers
from api.identity.router import router as auth_router
from api.intake.router import router as intake_router
from api.issue_reports.router import router as issues_router
from api.limits.body import BodyLimitMiddleware
from api.limits.http import PeerLimitMiddleware, limit_authenticated
from api.limits.rate import RatePolicy
from api.observability.middleware import RequestLoggingMiddleware
from api.support.action_router import router as support_action_router
from api.support.router import router as support_router
from api.system.router import router as system_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Resolve Flow API",
        version="0.1.0",
        lifespan=database_lifespan,
        responses={code: {"model": ErrorResponse} for code in (408, 413, 429, 503)},
    )
    app.state.rate_policy = RatePolicy.model_validate_json(
        os.getenv("REQUEST_LIMITS") or "{}"
    )
    install_error_handlers(app)

    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

    app.add_middleware(PeerLimitMiddleware)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(issues_router, dependencies=[Depends(limit_authenticated)])
    app.include_router(intake_router, dependencies=[Depends(limit_authenticated)])
    app.include_router(support_router, dependencies=[Depends(limit_authenticated)])
    app.include_router(
        support_action_router, dependencies=[Depends(limit_authenticated)]
    )
    return app


app = create_app()
