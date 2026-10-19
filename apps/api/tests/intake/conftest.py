import json
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from psycopg import AsyncConnection, sql
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.db.models import Base, CustomerAccount, IssueReport, User
from api.extraction.provider import ProviderResult
from api.intake.provider import OfflineIntakeProvider
from api.intake.runtime import IntakeRuntime
from api.intake.service import IntakeService
from api.workflow.checkpoints import postgres_connection_url, setup_checkpoints


class CountingProvider(OfflineIntakeProvider):
    def __init__(self):
        self.calls = 0

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        self.calls += 1
        return await super().generate(instructions, input_text, output_schema)


@dataclass
class Environment:
    url: str
    schema: str
    sessions: async_sessionmaker[AsyncSession]
    runtime: IntakeRuntime
    provider: CountingProvider
    report_id: UUID
    user_id: UUID
    other_account: UUID
    tokens: dict[str, str]

    def service(self, token: str = "customer-a") -> IntakeService:
        return IntakeService(self.runtime, token)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def environment(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[Environment]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for durable intake tests")
    url = postgres_connection_url(url)
    schema = f"rf_intake_{uuid4().hex}"
    async with await AsyncConnection.connect(url, autocommit=True) as connection:
        await connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
        )
    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+psycopg://"),
        connect_args={"options": f"-csearch_path={schema},public"},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(
                    conn,
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
                        )
                    ],
                )
            )
        await setup_checkpoints(url, f"{schema}_cp")
        async with sessions() as session:
            a, b = CustomerAccount(name="A"), CustomerAccount(name="B")
            session.add_all([a, b])
            await session.flush()
            users = [
                User(
                    customer_account_id=account,
                    user_type=kind,
                    name=name,
                    last_name="Fixture",
                )
                for account, kind, name in [
                    (a.id, "customer", "a"),
                    (a.id, "customer", "teammate"),
                    (b.id, "customer", "b"),
                    (None, "support", "support"),
                ]
            ]
            session.add_all(users)
            await session.flush()
            report = IssueReport(
                customer_account_id=a.id,
                submitted_by_user_id=users[0].id,
                description="My submitted issue report is missing from my list.",
                status="submitted",
            )
            session.add(report)
            await session.commit()
        tokens = dict(
            zip(
                ["customer-a", "teammate", "customer-b", "support"],
                [str(user.id) for user in users],
                strict=True,
            )
        )
        monkeypatch.setenv("DEMO_TOKEN_USER_IDS", json.dumps(tokens))
        provider = CountingProvider()
        runtime = IntakeRuntime(
            sessions, url, provider=provider, checkpoint_schema=f"{schema}_cp"
        )
        yield Environment(
            url,
            schema,
            sessions,
            runtime,
            provider,
            report.id,
            users[0].id,
            b.id,
            tokens,
        )
    finally:
        await engine.dispose()
        async with await AsyncConnection.connect(url, autocommit=True) as connection:
            for name in (f"{schema}_cp", schema):
                await connection.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(name)
                    )
                )
