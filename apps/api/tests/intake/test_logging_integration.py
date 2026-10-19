"""Correlate real durable execution/recovery requests through emitted JSON."""

import io
import json
import logging
from collections.abc import Generator

import pytest
from conftest import Environment
from httpx import AsyncClient
from test_support_actions import actions as actions
from test_support_actions import draft, reply

from api.observability import logger
from api.observability.config import SafeJSONFormatter
from api.support.action_schemas import SupportAction
from api.support.actions import SupportActions
from api.support.execution import DurableSimulation
from api.workflow.actions import ProposedAction
from api.workflow.approval import ApprovalDecision
from api.workflow.execution import SimulatedCreateTicketTool, ToolExecutionResult


@pytest.fixture
def log_output() -> Generator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SafeJSONFormatter())
    previous, level = logger.handlers[:], logger.level
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        logger.handlers = previous
        logger.setLevel(level)


@pytest.mark.anyio
async def test_recovery_has_new_request_id_same_execution_and_no_new_dispatch(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
    log_output: io.StringIO,
) -> None:
    e, service, client, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None and saved.proposal is not None
    original = DurableSimulation.complete

    async def interrupted(
        self: DurableSimulation,
        proposal: ProposedAction,
        approval: ApprovalDecision,
        result: ToolExecutionResult,
    ) -> None:
        raise RuntimeError("private simulated failure")

    monkeypatch.setattr(DurableSimulation, "complete", interrupted)
    base = f"/support/issue-reports/{e.report_id}/runs/{saved.run_id}"
    first = await client.post(
        base + "/decision", json=reply(saved).model_dump(mode="json")
    )
    assert first.status_code == 200 and first.json()["status"] == "execution_unknown"
    monkeypatch.setattr(DurableSimulation, "complete", original)
    recovered = await client.post(
        base + "/recover-execution", json=reply(saved).model_dump(mode="json")
    )
    assert recovered.status_code == 200
    assert SupportAction.model_validate(recovered.json()).status == "simulated_success"
    first_id, second_id = (
        first.headers["X-Request-ID"],
        recovered.headers["X-Request-ID"],
    )
    assert first_id != second_id and len(tool.calls) == 1
    rows = [json.loads(line) for line in log_output.getvalue().splitlines()]
    executions = [row for row in rows if row["event"] == "execution.completed"]
    assert {row["request_id"] for row in executions} == {first_id, second_id}
    assert {row["run_id"] for row in executions} == {str(saved.run_id)}
    assert {row["execution_id"] for row in executions} == {
        str(saved.proposal.idempotency_key)
    }
    assert any(
        row["event"] == "execution.receipt_reused" and row["request_id"] == second_id
        for row in rows
    )
    assert not any(
        row["event"] == "tool.started" and row["request_id"] == second_id
        for row in rows
    )
    assert any(
        row["event"] == "execution.result_committed" and row["request_id"] == second_id
        for row in rows
    )
    assert "private simulated failure" not in log_output.getvalue()
