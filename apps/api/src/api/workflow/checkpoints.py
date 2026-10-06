"""PostgreSQL checkpoint lifetime, schema setup, and typed serialization."""

import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import (  # pyright: ignore[reportMissingTypeStubs]
    JsonPlusSerializer,
)
from psycopg import AsyncConnection, sql
from psycopg.rows import DictRow, dict_row
from sqlalchemy.engine import make_url

from api.extraction.clarification import ClarificationDecision, ClarificationReason
from api.extraction.provider import ModelSettings, ProviderFailureKind, ProviderUsage
from api.extraction.schemas import Confidence, ExtractionResult, Severity
from api.extraction.service import ExtractionCallRecord, ExtractionFailureReason
from api.workflow.actions import (
    ActionRisk,
    CreateTicketArguments,
    ProposedAction,
    RiskLevel,
)
from api.workflow.approval import ApprovalChoice, ApprovalDecision
from api.workflow.clarification import ClarificationTurn, PendingClarification
from api.workflow.execution import (
    SimulatedTicketResult,
    ToolExecutionFailure,
    ToolExecutionResult,
)
from api.workflow.state import (
    CustomerSafeReport,
    DiagnosisDraft,
    ReportStatus,
    SafeWorkflowFailure,
)
from api.workflow.timeline import EventMetadata, EventType, ExecutionEvent

CHECKPOINT_SCHEMA = "workflow"


def checkpoint_serializer() -> JsonPlusSerializer:
    # Exact symbols only. No arbitrary application imports or pickle fallback.
    types = (
        ClarificationDecision,
        ClarificationReason,
        ModelSettings,
        ProviderFailureKind,
        ProviderUsage,
        Confidence,
        ExtractionResult,
        Severity,
        ExtractionCallRecord,
        ExtractionFailureReason,
        ClarificationTurn,
        PendingClarification,
        CustomerSafeReport,
        DiagnosisDraft,
        ReportStatus,
        SafeWorkflowFailure,
        ActionRisk,
        CreateTicketArguments,
        ProposedAction,
        RiskLevel,
        ApprovalChoice,
        ApprovalDecision,
        SimulatedTicketResult,
        ToolExecutionResult,
        ToolExecutionFailure,
        EventMetadata,
        EventType,
        ExecutionEvent,
    )
    symbols = [(kind.__module__, kind.__name__) for kind in types]
    return JsonPlusSerializer(
        allowed_msgpack_modules=symbols,
        allowed_json_modules=symbols,
        pickle_fallback=False,
    )


def workflow_config(run_id: UUID) -> RunnableConfig:
    return {"configurable": {"thread_id": str(run_id)}}


def validate_schema(schema: str) -> None:
    if re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema) is None:
        raise ValueError("Checkpoint schema must be a lowercase PostgreSQL identifier")


def postgres_connection_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.drivername not in {"postgresql", "postgres", "postgresql+psycopg"}:
        raise ValueError("Checkpoints require a PostgreSQL database URL")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


@asynccontextmanager
async def _connection(
    database_url: str, schema: str, *, create_schema: bool = False
) -> AsyncGenerator[AsyncConnection[DictRow]]:
    validate_schema(schema)
    async with await AsyncConnection[DictRow].connect(
        postgres_connection_url(database_url),
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    ) as connection:
        if create_schema:
            await connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
            )
        else:
            cursor = await connection.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,)
            )
            if await cursor.fetchone() is None:
                raise RuntimeError("Run checkpoint setup before opening the workflow")
        await connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
        )
        yield connection


async def setup_checkpoints(database_url: str, schema: str = CHECKPOINT_SCHEMA) -> None:
    """Explicitly create the schema and run the checkpointer's own migrations."""
    async with _connection(database_url, schema, create_schema=True) as connection:
        saver = AsyncPostgresSaver(connection, serde=checkpoint_serializer())
        await saver.setup()


@asynccontextmanager
async def open_checkpointer(
    database_url: str, schema: str = CHECKPOINT_SCHEMA
) -> AsyncGenerator[AsyncPostgresSaver]:
    """Keep this context open for every graph read/invoke that uses the saver."""
    async with _connection(database_url, schema) as connection:
        yield AsyncPostgresSaver(connection, serde=checkpoint_serializer())
