import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.extraction.provider import LLMProvider, OpenAIProvider
from api.intake.locks import IntakeLocks
from api.intake.projection import Mode
from api.intake.provider import OfflineIntakeProvider
from api.workflow.checkpoints import CHECKPOINT_SCHEMA, open_checkpointer
from api.workflow.graph import ReportLoader, build_workflow
from api.workflow.langgraph_types import WorkflowGraph
from api.workflow.state import WorkflowInput


class IntakeRuntime:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        database_url: str,
        *,
        mode: Mode = "offline",
        provider: LLMProvider | None = None,
        checkpoint_schema: str = CHECKPOINT_SCHEMA,
    ):
        if mode == "live" and provider is None:
            raise ValueError("Live intake requires an explicit provider")
        self.sessions = sessions
        self.database_url = database_url
        self.mode: Mode = mode
        self.provider = provider if provider is not None else OfflineIntakeProvider()
        self.checkpoint_schema = checkpoint_schema
        self.locks = IntakeLocks(database_url)

    @classmethod
    def configured(
        cls, sessions: async_sessionmaker[AsyncSession], database_url: str
    ) -> "IntakeRuntime":
        mode = os.getenv("INTAKE_PROVIDER_MODE", "offline")
        if mode == "offline":
            return cls(sessions, database_url)
        if mode == "live":
            model = os.environ["OPENAI_MODEL"]
            return cls(
                sessions, database_url, mode="live", provider=OpenAIProvider(model)
            )
        raise ValueError("Unsupported intake provider mode")

    @asynccontextmanager
    async def graph(
        self, loader: ReportLoader
    ) -> AsyncGenerator[WorkflowGraph[WorkflowInput]]:
        async with open_checkpointer(
            self.database_url, self.checkpoint_schema
        ) as saver:
            yield build_workflow(loader, self.provider, checkpointer=saver)

    async def close(self) -> None:
        if isinstance(self.provider, OpenAIProvider):
            await self.provider.client.close()
