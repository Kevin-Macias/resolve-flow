import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from conftest import CountingProvider, Environment
from sqlalchemy import select
from test_lifecycle import reply

from api.intake.models import IntakeOperation, IntakeRun
from api.intake.schemas import CustomerRun
from api.intake.service import IntakeService
from api.workflow.checkpoints import open_checkpointer, workflow_config

# Frozen control-channel fixture for the installed LangGraph persistence format.
RESUME = "__resume__"
NULL_TASK_ID = "00000000-0000-0000-0000-000000000000"


class Crash(BaseException):
    """Simulate process loss rather than a handled application exception."""


class BeforeDispatch(IntakeService):
    async def execute(self, run_id: UUID) -> None:
        raise Crash()


class BeforePublication(IntakeService):
    @staticmethod
    def publish(run: IntakeRun, view: CustomerRun) -> None:
        if not view.operation_pending:
            raise Crash()
        IntakeService.publish(run, view)


@pytest.mark.anyio
async def test_recover_start_before_dispatch_and_no_read_side_effects(
    environment: Environment,
) -> None:
    e = environment
    with pytest.raises(Crash):
        await BeforeDispatch(e.runtime, "customer-a").start(e.report_id)
    view = await e.service().for_report(e.report_id)
    assert view.operation_pending and view.revision == 1 and e.provider.calls == 0
    duplicate, created = await e.service().start(e.report_id)
    assert duplicate == view and not created and e.provider.calls == 0
    recovered = await e.service().recover(view.run_id, view.revision)
    assert recovered.status == "needs_clarification" and e.provider.calls == 1


@pytest.mark.anyio
async def test_checkpoint_result_recovered_without_repeating_provider(
    environment: Environment,
) -> None:
    e = environment
    with pytest.raises(Crash):
        await BeforePublication(e.runtime, "customer-a").start(e.report_id)
    assert e.provider.calls == 1
    pending = await e.service().for_report(e.report_id)
    recovered = await e.service().recover(pending.run_id, pending.revision)
    assert recovered.pending is not None and recovered.revision > pending.revision
    assert e.provider.calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize("after_checkpoint", [False, True])
async def test_resume_recovery_never_duplicates_answers(
    environment: Environment, after_checkpoint: bool
) -> None:
    e = environment
    view, _ = await e.service().start(e.report_id)
    request = reply(view)
    service = (
        BeforePublication(e.runtime, "customer-a")
        if after_checkpoint
        else BeforeDispatch(e.runtime, "customer-a")
    )
    with pytest.raises(Crash):
        await service.clarify(view.run_id, request)
    calls = e.provider.calls
    current = await e.service().get(view.run_id)
    duplicate = await e.service().clarify(view.run_id, request)
    assert duplicate == current and e.provider.calls == calls
    recovered = await e.service().recover(view.run_id, current.revision)
    assert recovered.status == "needs_confirmation" and len(recovered.turns) == 1
    assert e.provider.calls == 2
    assert recovered.turns[0].answers == request.answers
    async with e.sessions() as session:
        records = (await session.scalars(select(IntakeOperation))).all()
        assert len(records) == 2 and all(record.completed for record in records)


@pytest.mark.anyio
async def test_resume_already_written_before_answer_node_commits(
    environment: Environment,
) -> None:
    e = environment
    view, _ = await e.service().start(e.report_id)
    request = reply(view)
    with pytest.raises(Crash):
        await BeforeDispatch(e.runtime, "customer-a").clarify(view.run_id, request)
    # Write the resume control input exactly as the installed LangGraph does,
    # then "restart" without executing the interrupted node.
    async with e.runtime.graph(lambda _: asyncio.sleep(0, result="fixture")) as graph:
        snapshot = await graph.aget_state(workflow_config(view.run_id))
        interrupt = next(item for task in snapshot.tasks for item in task.interrupts)
    async with open_checkpointer(e.url, e.runtime.checkpoint_schema) as saver:
        await saver.aput_writes(
            snapshot.config, [(RESUME, {interrupt.id: request.reply()})], NULL_TASK_ID
        )
    current = await e.service().get(view.run_id)
    recovered = await e.service().recover(view.run_id, current.revision)
    assert recovered.status == "needs_confirmation" and len(recovered.turns) == 1
    assert e.provider.calls == 2


@pytest.mark.anyio
async def test_restart_in_separate_process_reads_and_recovers_persisted_state(
    environment: Environment,
) -> None:
    e = environment
    with pytest.raises(Crash):
        await BeforePublication(e.runtime, "customer-a").start(e.report_id)
    view = await e.service().for_report(e.report_id)
    worker = Path(__file__).with_name("restart_worker.py")
    env = {**os.environ, "DEMO_TOKEN_USER_IDS": json.dumps(e.tokens)}
    result = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            str(worker),
            e.url,
            e.schema,
            str(view.run_id),
            str(view.revision),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    output = json.loads(result.stdout)
    recovered = CustomerRun.model_validate_json(json.dumps(output["view"]))
    assert recovered.pending is not None and output["calls"] == 0
    assert recovered.revision > view.revision
    assert (await e.service().get(view.run_id)) == recovered


@pytest.mark.anyio
async def test_unknown_saved_reply_binding_fails_closed(
    environment: Environment,
) -> None:
    e = environment
    view, _ = await e.service().start(e.report_id)
    request = reply(view)
    with pytest.raises(Crash):
        await BeforeDispatch(e.runtime, "customer-a").clarify(view.run_id, request)
    # Corrupt the saved request and its checksum to emulate an inconsistent
    # privileged record, rather than merely malformed HTTP input.
    from fastapi import HTTPException

    from api.intake.service import payload_hash

    async with e.sessions() as session:
        operation = await session.get(
            IntakeOperation, (view.run_id, request.operation_id)
        )
        assert operation is not None
        operation.payload = {**operation.payload, "pending_id": str(uuid4())}
        operation.payload_hash = payload_hash(operation.payload)
        await session.commit()
    current = await e.service().get(view.run_id)
    with pytest.raises(HTTPException) as caught:
        await e.service().recover(view.run_id, current.revision)
    assert caught.value.status_code == 503 and e.provider.calls == 1
    assert (await e.service().get(view.run_id)).status == "failed"


@pytest.mark.anyio
async def test_cancel_after_committed_answer_recovers_only_unfinished_work(
    environment: Environment,
) -> None:
    from pydantic import BaseModel

    from api.extraction.provider import ProviderResult

    e = environment
    view, _ = await e.service().start(e.report_id)
    started = asyncio.Event()

    class Blocking(CountingProvider):
        async def generate(
            self,
            instructions: str,
            input_text: str,
            output_schema: type[BaseModel] | None = None,
        ) -> ProviderResult:
            started.set()
            await asyncio.Event().wait()
            return await super().generate(instructions, input_text, output_schema)

    e.runtime.provider = Blocking()
    task = asyncio.create_task(e.service().clarify(view.run_id, reply(view)))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    current = await e.service().get(view.run_id)
    assert current.operation_pending
    e.runtime.provider = e.provider
    recovered = await e.service().recover(view.run_id, current.revision)
    assert recovered.status == "needs_confirmation" and len(recovered.turns) == 1
    assert e.provider.calls == 2
