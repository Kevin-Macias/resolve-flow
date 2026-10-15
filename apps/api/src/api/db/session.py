import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from openai import OpenAIError
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.intake.runtime import IntakeRuntime
from api.system.service import DatabaseNotConfiguredError


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncGenerator[None]:
    from api.support.actions import SupportActions
    from api.support.evidence import SupportEvidenceService
    from api.support.metrics import SupportMetricsReader
    from api.support.reports import SupportReportStates
    from api.support.runs import SupportRuns

    app.state.intake_runtime = None
    app.state.support_runs = None
    app.state.support_report_states = None
    app.state.support_evidence = None
    app.state.support_metrics = None
    app.state.support_actions = None
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        app.state.session_factory = None
        yield
        return

    sqlalchemy_url = make_url(db_url).set(drivername="postgresql+psycopg")
    engine = create_async_engine(sqlalchemy_url)
    app.state.session_factory = async_sessionmaker[AsyncSession](
        engine, expire_on_commit=False
    )
    app.state.support_metrics = SupportMetricsReader(app.state.session_factory, db_url)
    app.state.support_runs = SupportRuns(app.state.session_factory, db_url)
    app.state.support_report_states = SupportReportStates(app.state.session_factory)
    app.state.support_evidence = SupportEvidenceService(
        app.state.session_factory, db_url
    )
    app.state.support_actions = SupportActions(app.state.session_factory, db_url)

    runtime: IntakeRuntime | None = None
    try:
        try:
            runtime = IntakeRuntime.configured(app.state.session_factory, db_url)
        except (ValueError, KeyError, OpenAIError):
            runtime = None
        app.state.intake_runtime = runtime
        yield
    finally:
        app.state.intake_runtime = None
        app.state.support_runs = None
        app.state.support_report_states = None
        app.state.support_evidence = None
        app.state.support_metrics = None
        app.state.support_actions = None
        try:
            if runtime is not None:
                await runtime.close()
        finally:
            app.state.session_factory = None
            await engine.dispose()


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] | None = (
        request.app.state.session_factory
    )
    if session_factory is None:
        raise DatabaseNotConfiguredError()

    async with session_factory() as session:
        yield session
