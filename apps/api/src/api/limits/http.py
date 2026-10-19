"""Peer limits before parsing; user limits before resource handlers."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp, Receive, Scope, Send

from api.db.session import get_session
from api.errors import error_response
from api.identity.context import RequestContext
from api.identity.dependencies import get_request_context
from api.limits.rate import Budget, RateLimiter, RatePolicy

RESOURCE_PREFIXES = ("/issue-reports", "/intake-runs", "/support", "/admin", "/auth")
MUTATIONS = {"POST", "PUT", "PATCH", "DELETE"}
MODEL_ROUTES = {
    "/issue-reports/{report_id}/intake-run",
    "/intake-runs/{run_id}/clarification",
    "/intake-runs/{run_id}/recover",
    "/support/issue-reports/{report_id}/evidence-analyses",
}


def sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is None:
        raise HTTPException(503, "Request limits unavailable")
    return factory


class PeerLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] == "OPTIONS"
            or not any(
                scope["path"] == prefix or scope["path"].startswith(prefix + "/")
                for prefix in RESOURCE_PREFIXES
            )
        ):
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        policy: RatePolicy = request.app.state.rate_policy
        # Transport peer only. Forwarding headers supplied by callers never select
        # a bucket. The supported server disables Uvicorn proxy header rewriting.
        peer = request.client.host if request.client else "unknown"
        budgets = [Budget("peer", peer, policy.peer)]
        if request.url.path in ("/auth/login", "/auth/invitations/redeem"):
            budgets.append(Budget("authentication-peer", peer, policy.authentication))
        try:
            await RateLimiter(sessions(request)).reserve(tuple(budgets))
        except HTTPException as error:
            # No database still preserves the missing-identity response for private
            # routes; authenticated work always fails closed when limits fail.
            if (
                error.status_code == 503
                and not request.headers.get("Authorization")
                and not scope["path"].startswith("/auth/")
            ):
                error = HTTPException(401, "Identity required")
            await error_response(
                error.status_code, str(error.detail), headers=error.headers
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def limit_authenticated(
    request: Request,
    context: Annotated[RequestContext, Depends(get_request_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    # Authentication only reads here. End that transaction before independent
    # reservations and potentially long-running model work; endpoint SQL can
    # start a fresh transaction on the same dependency-managed session.
    await session.rollback()
    policy: RatePolicy = request.app.state.rate_policy
    user = str(context.user_id)
    budgets = [Budget("user", user, policy.user)]
    if request.method in MUTATIONS:
        budgets.append(Budget("mutations-user", user, policy.mutations))
        if context.customer_account_id is not None:
            budgets.append(
                Budget(
                    "mutations-account",
                    str(context.customer_account_id),
                    policy.mutations,
                )
            )
        if request.scope["route"].path in MODEL_ROUTES:
            budgets.extend(
                (
                    Budget("model-user", user, policy.model_operations),
                    Budget(
                        "model-global", "application", policy.global_model_operations
                    ),
                )
            )
            if context.customer_account_id is not None:
                budgets.append(
                    Budget(
                        "model-account",
                        str(context.customer_account_id),
                        policy.model_operations,
                    )
                )
    await RateLimiter(sessions(request)).reserve(tuple(budgets))
