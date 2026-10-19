"""Durable intent/effect receipts survive real process exit before checkpointing."""

import asyncio
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import Environment
from fastapi import HTTPException
from httpx import AsyncClient
from psycopg import AsyncConnection
from sqlalchemy import func, select
from test_support_actions import actions as actions
from test_support_actions import draft, reply

from api.db.models import IssueReport
from api.support.action_models import ExecutionOperation, SimulatedTicketEffect
from api.support.action_schemas import SupportAction
from api.support.actions import SupportActions
from api.support.execution import DurableSimulation
from api.workflow.approval import record_approval
from api.workflow.approval_graph import approval_config
from api.workflow.checkpoints import open_checkpointer
from api.workflow.execution import SimulatedCreateTicketTool
from api.workflow.timeline import EventMetadata, EventType, transition_event


async def worker(
    e: Environment, saved: SupportAction, mode: str
) -> subprocess.CompletedProcess[str]:
    result = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            str(Path(__file__).with_name("execution_worker.py")),
            e.url,
            e.schema,
            str(e.report_id),
            str(saved.run_id),
            reply(saved).model_dump_json(),
            mode,
        ],
        env={**os.environ, "PYTHONPATH": str(Path.cwd() / "src")},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode == 73:
        # Process exit closes sockets, but PostgreSQL can still be releasing its
        # session locks. Wait for that release before issuing a recovery command.
        # This is the existing intake report-lock namespace, not a new policy.
        key = int.from_bytes(
            hashlib.sha256(f"resolveflow:intake:{e.report_id}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        async with await AsyncConnection.connect(e.url, autocommit=True) as conn:
            await conn.execute("SET lock_timeout = '5s'")
            await conn.execute("SELECT pg_advisory_lock(%s)", (key,))
    return result


@pytest.mark.anyio
@pytest.mark.parametrize(
    "window", ["before_effect", "during_effect", "after_effect", "after_result"]
)
async def test_process_crash_and_separate_process_recovery(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    window: str,
) -> None:
    e, service, _, _ = actions
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None and saved.proposal is not None
    crashed = await worker(e, saved, window)
    assert crashed.returncode == 73, crashed.stderr
    pending = await service.get("support", e.report_id)
    assert pending.status == "approved_unconfirmed"
    assert (
        await service.decide("support", e.report_id, saved.run_id, reply(saved))
    ) == pending
    async with e.sessions() as session:
        operation = await session.get(
            ExecutionOperation, saved.proposal.idempotency_key
        )
        effect = await session.get(
            SimulatedTicketEffect, saved.proposal.idempotency_key
        )
        assert operation is not None
        assert (operation.result is not None) == (window == "after_result")
        assert (effect is not None) == (window in ("after_effect", "after_result"))
        committed_receipt = effect.result if effect else None
    restarted = await worker(e, saved, "recover")
    assert restarted.returncode == 0, restarted.stderr
    recovered = SupportAction.model_validate_json(restarted.stdout)
    assert recovered.status == "simulated_success" and recovered.execution is not None
    if committed_receipt:
        assert recovered.execution.model_dump(mode="json") == committed_receipt
    again = await service.recover("support", e.report_id, saved.run_id, reply(saved))
    assert again == recovered
    async with e.sessions() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(SimulatedTicketEffect)
            )
            == 1
        )
        operation = await session.get(
            ExecutionOperation, saved.proposal.idempotency_key
        )
        assert (
            operation is not None
            and operation.result == recovered.execution.model_dump(mode="json")
        )
    assert (
        sum(event.event_type == "tool_succeeded" for event in recovered.timeline) == 1
    )


@pytest.mark.anyio
async def test_recovery_preserves_approval_in_pending_checkpoint_writes(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, _, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.proposal is not None and saved.run_id is not None
    row = await service.registry(e.report_id)
    assert row is not None
    _, _, context = await service.observations("support", e.report_id)
    decision = record_approval(reply(saved), saved.proposal, context)
    async with service.stage("support", e.report_id, row) as stage:
        snapshot = await stage.aget_state(approval_config(saved.run_id))
    review = next(task for task in snapshot.tasks if task.name == "review_action")
    events = transition_event(
        saved.run_id,
        list(saved.timeline),
        "approval",
        EventType.ACTION_APPROVED,
        saved.proposal.fingerprint(),
        EventMetadata(
            action_id=saved.proposal.action_id,
            action_version=saved.proposal.version,
            fingerprint=saved.proposal.fingerprint(),
            actor_id=context.user_id,
        ),
    )
    # Freeze the installed checkpointer's node-write boundary. The main snapshot
    # still lacks approval, while aget_state can already read these durable writes.
    async with open_checkpointer(e.url, e.runtime.checkpoint_schema) as saver:
        await saver.aput_writes(
            snapshot.config, [("approval", decision), ("timeline", events)], review.id
        )
        raw = await saver.aget_tuple(approval_config(saved.run_id))
        assert raw is not None and "approval" not in raw.checkpoint["channel_values"]
    execution = await service.simulation("support", e.report_id, row).execute(
        saved.proposal,
        decision,
        context,
        tool,
    )
    observed = await service.get("support", e.report_id)
    assert observed.decision == decision and len(observed.timeline) == 2
    recovered = await service.recover(
        "support", e.report_id, saved.run_id, reply(saved)
    )
    assert recovered.decision == decision and recovered.execution == execution
    assert [event.event_type for event in recovered.timeline] == [
        "approval_requested",
        "action_approved",
        "tool_succeeded",
    ]
    assert (await service.get("support", e.report_id)) == recovered
    assert len(tool.calls) == 1


@pytest.mark.anyio
async def test_unknown_failure_requires_explicit_recovery(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e, service, client, tool = actions
    original = DurableSimulation.complete

    async def fail(*args: object) -> None:
        raise RuntimeError("private publication failure")

    monkeypatch.setattr(DurableSimulation, "complete", fail)
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None
    failed = await service.decide("support", e.report_id, saved.run_id, reply(saved))
    assert failed.status == "execution_unknown" and len(tool.calls) == 1
    assert (await service.get("support", e.report_id)) == failed
    assert (
        await service.decide("support", e.report_id, saved.run_id, reply(saved))
    ) == failed
    monkeypatch.setattr(DurableSimulation, "complete", original)
    response = await client.post(
        f"/support/issue-reports/{e.report_id}/runs/{saved.run_id}/recover-execution",
        json=reply(saved).model_dump(mode="json"),
    )
    assert response.status_code == 200, response.text
    recovered = SupportAction.model_validate(response.json())
    assert recovered.status == "simulated_success" and recovered.failure is None
    assert len(tool.calls) == 1
    assert [event.event_type for event in recovered.timeline][-2:] == [
        "tool_failed",
        "tool_succeeded",
    ]


@pytest.mark.anyio
async def test_destination_concurrent_replay_and_changed_key_binding(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, _, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None and saved.proposal is not None
    completed = await service.decide("support", e.report_id, saved.run_id, reply(saved))
    assert completed.decision is not None and completed.execution is not None
    context = await service.observations("support", e.report_id)
    simulation = DurableSimulation(e.sessions, saved.run_id)
    receipts = await asyncio.gather(
        *(
            simulation.destination(saved.proposal, completed.decision, context[2], tool)
            for _ in range(3)
        )
    )
    assert (
        all(result == completed.execution for result in receipts)
        and len(tool.calls) == 1
    )
    changed = saved.proposal.model_copy(
        update={"explanation": "Different approved request"}
    )
    changed_approval = record_approval(
        reply(saved).model_copy(update={"fingerprint": changed.fingerprint()}),
        changed,
        context[2],
    )
    with pytest.raises(ValueError, match="receipt"):
        await simulation.destination(changed, changed_approval, context[2], tool)
    assert len(tool.calls) == 1


@pytest.mark.anyio
async def test_recovery_never_dispatches_without_matching_saved_approval(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e, service, client, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    path = f"/support/issue-reports/{e.report_id}/runs/{saved.run_id}/recover-execution"
    assert (
        await client.post(path, json=reply(saved).model_dump(mode="json"))
    ).status_code == 409
    assert saved.run_id is not None
    rejected = await service.decide(
        "support", e.report_id, saved.run_id, reply(saved, "reject")
    )
    assert rejected.status == "rejected"
    assert (
        await client.post(path, json=reply(saved).model_dump(mode="json"))
    ).status_code == 409
    assert not tool.calls

    def forbid_foreign_lock(run_id: object) -> None:
        pytest.fail("Must reject a foreign run before locking it")

    monkeypatch.setattr(service, "run_locks", forbid_foreign_lock)
    assert (
        await client.post(
            f"/support/issue-reports/{e.report_id}/runs/{uuid4()}/recover-execution",
            json=reply(saved).model_dump(mode="json"),
        )
    ).status_code == 404


@pytest.mark.anyio
async def test_legacy_unknown_without_operation_stays_manual(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, _, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None
    row = await service.registry(e.report_id)
    assert row is not None and saved.proposal is not None
    _, _, context = await service.observations("support", e.report_id)
    async with service.stage("support", e.report_id, row) as stage:
        await stage.aupdate_state(
            approval_config(saved.run_id),
            {"approval": record_approval(reply(saved), saved.proposal, context)},
            as_node="review_action",
        )
    with pytest.raises(HTTPException, match="manual review") as error:
        await service.recover("support", e.report_id, saved.run_id, reply(saved))
    assert error.value.status_code == 409 and not tool.calls


@pytest.mark.anyio
async def test_operation_key_and_run_cannot_be_rebound(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, _, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None and saved.proposal is not None
    completed = await service.decide("support", e.report_id, saved.run_id, reply(saved))
    assert completed.decision is not None
    simulation = DurableSimulation(e.sessions, saved.run_id)
    for field in ("explanation", "idempotency_key"):
        changed = saved.proposal.model_copy(
            update={
                field: "Changed request" if field == "explanation" else uuid4(),
            }
        )
        approval = record_approval(
            reply(saved).model_copy(update={"fingerprint": changed.fingerprint()}),
            changed,
            (await service.observations("support", e.report_id))[2],
        )
        with pytest.raises(ValueError):
            await simulation.reserve(changed, approval)
    assert len(tool.calls) == 1


@pytest.mark.anyio
async def test_concurrent_explicit_recovery_creates_one_effect(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
) -> None:
    e, service, _, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    assert saved.run_id is not None
    crashed = await worker(e, saved, "before_effect")
    assert crashed.returncode == 73, crashed.stderr
    outcomes = await asyncio.gather(
        service.recover("support", e.report_id, saved.run_id, reply(saved)),
        service.recover("support", e.report_id, saved.run_id, reply(saved)),
        return_exceptions=True,
    )
    assert any(isinstance(result, SupportAction) for result in outcomes), outcomes
    assert all(
        isinstance(result, SupportAction)
        or isinstance(result, HTTPException)
        and result.status_code == 409
        for result in outcomes
    )
    # The existing report lock returns busy rather than waiting. A later replay
    # must still return exactly the same outcome without another effect.
    final = await service.recover("support", e.report_id, saved.run_id, reply(saved))
    assert final.status == "simulated_success"
    assert all(
        result == final for result in outcomes if isinstance(result, SupportAction)
    )
    assert len(tool.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["grants", "archive", "input", "fingerprint"])
async def test_recovery_preserves_access_freshness_and_proposal_checks(
    actions: tuple[Environment, SupportActions, AsyncClient, SimulatedCreateTicketTool],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    e, service, client, tool = actions
    saved = await service.prepare("support", e.report_id, draft())
    crashed = await worker(e, saved, "after_effect")
    assert crashed.returncode == 73, crashed.stderr
    body = reply(saved)
    if change == "grants":
        monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", "{}")
    elif change == "fingerprint":
        body = body.model_copy(update={"fingerprint": "0" * 64})
    else:
        async with e.sessions() as session:
            report = await session.get(IssueReport, e.report_id)
            assert report is not None
            if change == "archive":
                report.status = "deleted"
            else:
                report.description += " New observation."
            await session.commit()
    response = await client.post(
        f"/support/issue-reports/{e.report_id}/runs/{saved.run_id}/recover-execution",
        json=body.model_dump(mode="json"),
    )
    assert response.status_code == (404 if change == "grants" else 409)
    assert not tool.calls
    async with e.sessions() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(SimulatedTicketEffect)
            )
            == 1
        )
