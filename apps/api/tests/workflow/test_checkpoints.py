"""Typed checkpoint round trips and actual PostgreSQL process restarts."""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from psycopg import connect, sql

from api.extraction.clarification import ClarificationDecision, ClarificationReason
from api.extraction.provider import ModelSettings, ProviderFailureKind, ProviderUsage
from api.extraction.schemas import Confidence, ExtractionResult, Severity
from api.extraction.service import ExtractionCallRecord, ExtractionFailureReason
from api.workflow.checkpoints import (
    checkpoint_serializer,
    open_checkpointer,
    postgres_connection_url,
    setup_checkpoints,
    validate_schema,
    workflow_config,
)
from api.workflow.clarification import ClarificationTurn, PendingClarification
from api.workflow.state import (
    CustomerSafeReport,
    DiagnosisDraft,
    ReportStatus,
    SafeWorkflowFailure,
)


@pytest.fixture
def checkpoint_database() -> Iterator[tuple[str, str]]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL checkpoint tests")
    schema = f"rf_checkpoint_test_{uuid4().hex}"
    try:
        asyncio.run(setup_checkpoints(url, schema))
        # The library owns checkpoint migrations; explicit setup is repeatable.
        asyncio.run(setup_checkpoints(url, schema))
        yield url, schema
    finally:
        with connect(postgres_connection_url(url), autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema)
                )
            )
            row = connection.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,)
            ).fetchone()
            assert row is None, "Checkpoint test schema survived cleanup"


def test_state_values_restore_with_their_application_types() -> None:
    extraction = ExtractionResult(
        summary="Synthetic report",
        service_code="payments",
        severity=Severity.LOW,
        confidence=Confidence.HIGH,
        reported_facts=["Reported inconvenience"],
        missing_data=[],
        contradictions=[],
        questions=[],
    )
    values: tuple[object, ...] = (
        uuid4(),
        extraction,
        ClarificationDecision((ClarificationReason.UNKNOWN_SEVERITY,), ("Impact?",)),
        ExtractionCallRecord(
            "test-prompt",
            "3",
            ModelSettings("fake", reasoning_effort="low"),
            "ExtractionResult",
            attempts=2,
            usage=ProviderUsage(10, 5, 15),
        ),
        ClarificationTurn(round_number=1, questions=("Impact?",), answers=("Low",)),
        PendingClarification(
            pending_id=uuid4(),
            round_number=None,
            questions=(),
            reasons=(ClarificationReason.UNKNOWN_SEVERITY,),
            mode="continue_only",
            cause="round_limit",
        ),
        DiagnosisDraft(("Reported inconvenience",), (), ()),
        CustomerSafeReport(ReportStatus.NEEDS_CONFIRMATION, "Confirm", incomplete=True),
        SafeWorkflowFailure(
            "classify",
            ExtractionFailureReason.PROVIDER_ERROR,
            ProviderFailureKind.TIMEOUT,
        ),
    )
    serde = checkpoint_serializer()
    for original in values:
        restored: object = serde.loads_typed(serde.dumps_typed(original))
        assert type(restored) is type(original)
        assert restored == original
    assert serde.pickle_fallback is False


@pytest.mark.parametrize(
    "schema", ["workflow; DROP TABLE reports", "public.workflow", "", "a" * 64]
)
def test_invalid_schema_is_rejected(schema: str) -> None:
    with pytest.raises(ValueError):
        validate_schema(schema)


def test_config_uses_the_run_uuid_and_url_conversion_preserves_credentials() -> None:
    run_id = uuid4()
    assert workflow_config(run_id) == {"configurable": {"thread_id": str(run_id)}}
    assert (
        postgres_connection_url("postgresql+psycopg://user:password@localhost/db")
        == "postgresql://user:password@localhost/db"
    )
    with pytest.raises(ValueError):
        postgres_connection_url("sqlite:///test.db")


def worker(mode: str, run_id: UUID, report_id: UUID, schema: str) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("checkpoint_worker.py")),
            mode,
            str(run_id),
            str(report_id),
            schema,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_resume_after_real_process_restart(
    checkpoint_database: tuple[str, str],
) -> None:
    _, schema = checkpoint_database
    run_id, report_id = uuid4(), uuid4()
    first = worker("start", run_id, report_id, schema)
    assert first["model_calls"] == 1
    assert first["next"] == ["clarify"]
    # Each worker exits and closes its saver; the next creates a new graph/process.
    second = worker("answer", run_id, report_id, schema)
    assert second["turn_count"] == 1
    assert second["model_calls"] == 1
    assert second["pending"] != first["pending"]
    third = worker("continue", run_id, report_id, schema)
    assert third["model_calls"] == 0
    assert third["turn_count"] == 1
    assert third["continued_incomplete"] is True
    assert third["pending"] is None
    fourth = worker("inspect", run_id, report_id, schema)
    assert fourth["model_calls"] == 0
    assert fourth["timeline"] == third["timeline"]
    assert isinstance(first["timeline"], list)
    assert isinstance(second["timeline"], list)
    assert (
        second["timeline"][: len(cast(list[object], first["timeline"]))]
        == first["timeline"]
    )
    assert fourth["turn_count"] == 1
    assert fourth["run_id"] == str(run_id)
    assert fourth["report_id"] == str(report_id)
    assert fourth["model"] == "fake-restart"
    assert fourth["prompt_version"] == "3"


def test_missing_schema_requires_explicit_setup(
    checkpoint_database: tuple[str, str],
) -> None:
    url, _ = checkpoint_database

    async def open_missing() -> None:
        async with open_checkpointer(url, f"rf_missing_{uuid4().hex}"):
            pytest.fail("Missing schema should not open")

    with pytest.raises(RuntimeError, match="setup"):
        asyncio.run(open_missing())


def test_approval_pause_and_decision_survive_separate_processes(
    checkpoint_database: tuple[str, str],
) -> None:
    _, schema = checkpoint_database
    run_id, report_id = uuid4(), uuid4()
    first = worker("approval-start", run_id, report_id, schema)
    assert first["approved"] is False
    second = worker("approval-approve", run_id, report_id, schema)
    assert second["approved"] is True
    assert second["action_id"] == first["action_id"]
    assert second["fingerprint"] == first["fingerprint"]
    assert second["key"] == first["key"]
    third = worker("approval-inspect", run_id, report_id, schema)
    assert third == second


def test_simulated_execution_result_restores_without_another_tool_call(
    checkpoint_database: tuple[str, str],
) -> None:
    _, schema = checkpoint_database
    run_id, report_id = uuid4(), uuid4()
    first = worker("tool-start", run_id, report_id, schema)
    assert first["execution"] is None
    assert first["tool_calls"] == 0
    second = worker("tool-approve", run_id, report_id, schema)
    assert second["approved"] is True
    assert second["tool_calls"] == 1
    third = worker("tool-inspect", run_id, report_id, schema)
    assert third["tool_calls"] == 0
    assert third["execution"] == second["execution"]
    assert third["fingerprint"] == first["fingerprint"]


def test_duplicate_approval_after_process_restart_reuses_execution(
    checkpoint_database: tuple[str, str],
) -> None:
    _, schema = checkpoint_database
    run_id, report_id = uuid4(), uuid4()
    worker("tool-start", run_id, report_id, schema)
    first = worker("tool-approve", run_id, report_id, schema)
    duplicate = worker("tool-approve", run_id, report_id, schema)
    assert first["tool_calls"] == 1
    assert duplicate["tool_calls"] == 0
    assert duplicate["execution"] == first["execution"]
    assert duplicate["decided_at"] == first["decided_at"]
    assert duplicate["timeline"] == first["timeline"]


def test_concurrent_processes_share_first_execution(
    checkpoint_database: tuple[str, str],
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    _, schema = checkpoint_database
    run_id, report_id = uuid4(), uuid4()
    worker("tool-start", run_id, report_id, schema)
    # Two distinct subprocesses, checkpointer connections, and lock connections.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(worker, "tool-approve", run_id, report_id, schema)
            for _ in range(2)
        ]
        results = [future.result() for future in futures]
    counts = [result["tool_calls"] for result in results]
    assert counts.count(0) == 1
    assert counts.count(1) == 1
    assert results[0]["execution"] == results[1]["execution"]
    assert results[0]["decided_at"] == results[1]["decided_at"]
    assert results[0]["timeline"] == results[1]["timeline"]


def test_failed_execution_survives_restart_without_retry(
    checkpoint_database: tuple[str, str],
) -> None:
    _, schema = checkpoint_database
    run_id, report_id = uuid4(), uuid4()
    worker("tool-start", run_id, report_id, schema)
    failed = worker("tool-fail", run_id, report_id, schema)
    assert failed["tool_calls"] == 1
    assert failed["execution"] is None
    restored = worker("tool-failed-replay", run_id, report_id, schema)
    assert restored["tool_calls"] == 0
    assert restored["failure"] == failed["failure"]
    assert restored["execution"] is None
    assert restored["timeline"] == failed["timeline"]
