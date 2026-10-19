"""A private schema pair for evaluation; never migrate or clear public tables."""

import json
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import patch
from uuid import UUID, uuid4

from psycopg import AsyncConnection, sql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.models import Base, CustomerAccount, IssueReport, Service, User
from api.evaluations.extraction import FixtureProvider
from api.extraction.provider import ProviderResult
from api.extraction.schemas import Confidence, ExtractionResult, Severity
from api.intake.runtime import IntakeRuntime
from api.intake.service import IntakeService
from api.support.action_models import (  # register tables
    ProposalPreparation,
    SupportActionRun,
)
from api.workflow.checkpoints import postgres_connection_url, setup_checkpoints


@dataclass
class EvaluationDatabase:
    sessions: async_sessionmaker[AsyncSession]
    url: str
    checkpoint_schema: str
    account_id: UUID
    customer_id: UUID

    async def report(self, description: str) -> UUID:
        async with self.sessions() as session:
            report = IssueReport(
                customer_account_id=self.account_id,
                submitted_by_user_id=self.customer_id,
                description=description,
                status="submitted",
            )
            session.add(report)
            await session.commit()
            return report.id

    async def completed_intake(self, report_id: UUID) -> None:
        result = ExtractionResult(
            summary="Fixture observation for manual support review",
            service_code="issue-reports",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            reported_facts=["Customer reports a missing issue report."],
            missing_data=[],
            contradictions=[],
            questions=[],
        )
        runtime = IntakeRuntime(
            self.sessions,
            self.url,
            provider=FixtureProvider([ProviderResult(text=result.model_dump_json())]),
            checkpoint_schema=self.checkpoint_schema,
        )
        view, _ = await IntakeService(runtime, "evaluation-customer").start(report_id)
        if view.status != "needs_confirmation":
            raise ValueError("Intake setup did not reach confirmation")


@asynccontextmanager
async def evaluation_database(raw_url: str) -> AsyncGenerator[EvaluationDatabase]:
    url = postgres_connection_url(raw_url)
    schema = f"rf_eval_{uuid4().hex}"
    checkpoint_schema = f"{schema}_cp"
    engine = create_async_engine(
        make_url(url).set(drivername="postgresql+psycopg"),
        connect_args={"options": f"-csearch_path={schema},public"},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with await AsyncConnection.connect(url, autocommit=True) as conn:
            await conn.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
            )
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync,
                    checkfirst=False,
                    tables=[
                        Base.metadata.tables[name]
                        for name in (
                            "customer_accounts",
                            "users",
                            "services",
                            "issue_reports",
                            "request_limit_windows",
                            "intake_runs",
                            "intake_operations",
                            "model_call_attempts",
                            SupportActionRun.__tablename__,
                            ProposalPreparation.__tablename__,
                            "execution_operations",
                            "simulated_ticket_effects",
                        )
                    ],
                )
            )
        await setup_checkpoints(url, checkpoint_schema)
        async with sessions() as session:
            account = CustomerAccount(name="Evaluation account A")
            session.add(account)
            await session.flush()
            customer = User(
                customer_account_id=account.id,
                user_type="customer",
                name="Fixture",
                last_name="Customer",
            )
            support = User(user_type="support", name="Fixture", last_name="Support")
            session.add_all(
                [
                    customer,
                    support,
                    Service(code="issue-reports", label="Issue reports"),
                ]
            )
            await session.commit()
        # The runner is a standalone process. Existing process configuration is
        # restored even on failure; credentials are never copied into reports.
        with patch.dict(
            os.environ,
            {
                "AUTH_MODE": "demo",
                "DEMO_TOKEN_USER_IDS": json.dumps(
                    {
                        "evaluation-customer": str(customer.id),
                        "evaluation-support": str(support.id),
                    }
                ),
                "DEMO_SUPPORT_ACCOUNT_IDS": json.dumps(
                    {str(support.id): [str(account.id)]}
                ),
            },
        ):
            yield EvaluationDatabase(
                sessions, url, checkpoint_schema, account.id, customer.id
            )
    finally:
        await engine.dispose()
        async with await AsyncConnection.connect(url, autocommit=True) as conn:
            for name in (checkpoint_schema, schema):
                await conn.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(name)
                    )
                )
