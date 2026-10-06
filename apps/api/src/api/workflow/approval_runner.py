"""Serialize approval submissions before reading or advancing saved state."""

import asyncio
import hashlib
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import cast
from uuid import UUID

from langgraph.graph.state import (  # pyright: ignore[reportMissingTypeStubs]
    CompiledStateGraph,
)
from langgraph.types import Command  # pyright: ignore[reportMissingTypeStubs]
from psycopg import AsyncConnection

from api.workflow.actions import ProposedAction
from api.workflow.approval import ApprovalDecision, matches, validate_approval_reply
from api.workflow.approval_graph import ApprovalContextLoader, approval_config
from api.workflow.checkpoints import postgres_connection_url
from api.workflow.state import ApprovalInput, ApprovalState

type RunLock = Callable[[UUID], AbstractAsyncContextManager[None]]


class MemoryRunLocks:
    """Share one instance across runners using the same in-memory checkpoint store."""

    def __init__(self) -> None:
        self._locks: dict[UUID, asyncio.Lock] = {}

    @asynccontextmanager
    async def __call__(self, run_id: UUID) -> AsyncGenerator[None]:
        async with self._locks.setdefault(run_id, asyncio.Lock()):
            yield


class PostgresRunLocks:
    """Session advisory locks coordinate workers using the same database/store.

    A dedicated connection holds each lock until checkpoint writes finish. A
    lost process releases its lock; effect reconciliation still belongs to RF-703.
    """

    def __init__(self, database_url: str, namespace: str = "workflow") -> None:
        self._url = postgres_connection_url(database_url)
        self._namespace = namespace

    @asynccontextmanager
    async def __call__(self, run_id: UUID) -> AsyncGenerator[None]:
        digest = hashlib.sha256(
            f"resolveflow:{self._namespace}:{run_id}:approval".encode()
        ).digest()
        key = int.from_bytes(digest[:8], "big", signed=True)
        async with await AsyncConnection.connect(self._url, autocommit=True) as conn:
            await conn.execute("SELECT pg_advisory_lock(%s)", (key,))
            # Closing the dedicated connection releases the session lock even
            # when an exception or cancellation interrupts graph execution.
            yield


class ApprovalRunner:
    """Trusted entry point; callers must not bypass it with raw graph mutations."""

    def __init__(
        self,
        stage: CompiledStateGraph[ApprovalState, None, ApprovalInput, ApprovalState],
        load_context: ApprovalContextLoader,
        lock: RunLock,
    ) -> None:
        self._stage = stage
        self._load_context = load_context
        self._lock = lock

    async def submit(self, run_id: UUID, reply: object) -> ApprovalState:
        async with self._lock(run_id):
            config = approval_config(run_id)
            snapshot = await self._stage.aget_state(config)
            if not snapshot.values:
                raise ValueError("Approval run does not exist")
            state = cast(ApprovalState, snapshot.values)
            if state["workflow_run_id"] != run_id:
                raise ValueError("Approval run identity mismatch")
            context = await self._load_context(state["issue_report_id"])
            if context.user_type != "support":
                raise PermissionError("Only authorized support can review an action")
            proposal = ProposedAction.model_validate(state["proposed_action"])
            if proposal.arguments.issue_report_id != state["issue_report_id"]:
                raise ValueError("Proposal must belong to this workflow's issue report")
            if validate_approval_reply(reply, proposal) is None:
                raise ValueError("Invalid or stale approval")
            decision = state.get("approval")
            if decision is not None:
                decision = ApprovalDecision.model_validate(decision)
                if not matches(decision, proposal):
                    raise ValueError("Saved decision belongs to a different proposal")
                # First accepted decision wins, including a rejection. A saved
                # approval with unfinished execution is not permission to retry.
                return state
            if not any(task.interrupts for task in snapshot.tasks):
                raise ValueError("Approval run is not awaiting a decision")
            await self._stage.ainvoke(
                Command(resume=reply), config, durability="sync"
            )
            completed = await self._stage.aget_state(config)
            return cast(ApprovalState, completed.values)
