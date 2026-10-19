"""Exercise actual scenarios and distinguish observations from uncomputed scores."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from psycopg import AsyncConnection

from api.evaluations.contracts import FROZEN_SHA256, Case, load_case_set
from api.evaluations.runner import execute_case, run_evaluation

ROOT = Path(__file__).resolve().parents[4]
DATA = load_case_set(ROOT / "knowledge/evaluations/workspace-v1.json")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "case",
    [case for case in DATA.cases if case.target != "approval"],
    ids=lambda c: c.case_id,
)
async def test_offline_targets_execute_without_expected_driving_outputs(case: Case):
    result = await execute_case(case, DATA, ROOT, None)
    assert result.execution_status == "completed", result.model_dump_json()
    assert result.observed is not None
    assert result.expected == case.expected
    assert all(
        a.status in ("unmeasured", "not_applicable")
        for a in result.assessments.values()
    )
    if case.target == "extraction":
        assert result.observed["provider_calls"] == 1
    if case.case_id == "RF602-F01":
        assert result.observed["extraction_failure"] == "provider_error"
        assert result.observed["provider_failure"] == "timeout"
        assert result.observed["attempts"] == 3
    if case.case_id == "RF602-A02":
        assert result.observed["output_rejected"] is True
        assert result.observed["source_round_trips_as_data"] is True
    if case.case_id in ("RF602-A03", "RF602-A04"):
        assert result.observed["returned_sections"] == [
            {
                "document_id": "archived-report",
                "version": "1",
                "heading": "Interpretation",
            }
        ]


@pytest.mark.anyio
async def test_expected_label_change_does_not_change_observed_output():
    original = DATA.cases[0]
    changed = original.model_copy(
        update={"expected": {"severity_allowed": ["critical"]}}
    )
    first = await execute_case(original, DATA, ROOT, None)
    second = await execute_case(changed, DATA, ROOT, None)
    assert first.observed == second.observed
    assert first.expected != second.expected


@pytest.mark.anyio
async def test_unexpected_errors_are_sanitized_and_do_not_become_expected_failures():
    case = DATA.cases[0].model_copy(
        update={"setup": {"provider_response_fixture": "private-fixture-exception"}}
    )
    result = await execute_case(case, DATA, ROOT, None)
    assert result.error == "case_execution_failed" and result.observed is None
    assert "private-fixture-exception" not in result.model_dump_json()
    assert result.execution_status == "error"


@pytest.mark.anyio
async def test_outer_timeout_and_cancellation():
    result = await execute_case(
        next(c for c in DATA.cases if c.case_id == "RF602-F01"),
        DATA,
        ROOT,
        None,
        timeout_seconds=0,
    )
    assert result.error == "case_timeout"
    task = asyncio.create_task(execute_case(DATA.cases[0], DATA, ROOT, None))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_modified_artifact_rejected_before_execution(tmp_path: Path):
    path = tmp_path / "cases.json"
    path.write_text(
        (ROOT / "knowledge/evaluations/workspace-v1.json").read_text() + " "
    )
    with pytest.raises(ValueError, match="frozen"):
        load_case_set(path)


def test_cli_requires_explicit_database_and_rejects_live():
    environment = os.environ.copy()
    environment.pop("EVALUATION_DATABASE_URL", None)
    for args in ([], ["--live"]):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "apps/api/scripts/evaluate_workspace.py"),
                *args,
            ],
            env=environment,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 2
        assert not completed.stdout


@pytest.mark.anyio
async def test_full_run_repeats_and_cleans_owned_schemas():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for isolated runner integration")
    async with await AsyncConnection.connect(url, autocommit=True) as connection:
        before = await (
            await connection.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'rf_eval_%' ORDER BY schema_name"
            )
        ).fetchall()
    first = await run_evaluation(ROOT, url)
    second = await run_evaluation(ROOT, url)
    assert first.error_cases == 0, first.model_dump_json()
    assert first.completed_cases == 20 and len(first.cases) == 20
    assert first.case_set_sha256 == FROZEN_SHA256
    assert first.quality_measured is False
    assert [c.expected for c in first.cases] == [c.expected for c in second.cases]
    by_id = {c.case_id: c for c in first.cases}
    for cid, count, status in [
        ("RF602-S04", 1, "simulated_success"),
        ("RF602-S05", 0, "rejected"),
        ("RF602-A05", 0, "awaiting_decision"),
        ("RF602-F04", 1, "execution_unknown"),
        ("RF602-F05", 1, "approved_unconfirmed"),
    ]:
        observed = by_id[cid].observed
        assert (
            observed
            and observed["tool_dispatches"] == count
            and observed["execution_status"] == status
        )
    stale = by_id["RF602-A05"].observed
    assert stale is not None and stale["decision_request_statuses"] == [409]
    serialized = first.model_dump_json()
    assert "RF602 private fixture exception" not in serialized
    assert "This fictional note belongs only to account B." not in serialized
    assert url not in serialized
    async with await AsyncConnection.connect(url, autocommit=True) as connection:
        after = await (
            await connection.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'rf_eval_%' ORDER BY schema_name"
            )
        ).fetchall()
    assert before == after


def test_cli_does_not_overwrite_an_existing_report(tmp_path: Path):
    destination = tmp_path / "report.json"
    destination.write_text("keep this report")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "apps/api/scripts/evaluate_workspace.py"),
            "--database-url",
            "not-a-database",
            "--output",
            str(destination),
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert destination.read_text() == "keep this report"
    assert not completed.stdout


@pytest.mark.anyio
async def test_cancellation_cleans_owned_schemas_and_restores_identity_environment():
    from api.evaluations.database import evaluation_database

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for cancellation cleanup")
    original = os.environ.get("DEMO_TOKEN_USER_IDS")
    async with await AsyncConnection.connect(url, autocommit=True) as connection:
        before = await (
            await connection.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'rf_eval_%' ORDER BY schema_name"
            )
        ).fetchall()
    with pytest.raises(asyncio.CancelledError):
        async with evaluation_database(url) as database:
            await database.report("Disposable cancellation fixture.")
            raise asyncio.CancelledError()
    assert os.environ.get("DEMO_TOKEN_USER_IDS") == original
    async with await AsyncConnection.connect(url, autocommit=True) as connection:
        after = await (
            await connection.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'rf_eval_%' ORDER BY schema_name"
            )
        ).fetchall()
    assert before == after


@pytest.mark.anyio
async def test_one_failed_executor_does_not_discard_later_cases(
    monkeypatch: pytest.MonkeyPatch,
):
    from api.evaluations import runner
    from api.evaluations.contracts import CaseSet, Values

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for partial run integration")
    original = runner.execute_extraction
    first = True

    async def failing_once(case: Case, data: CaseSet) -> Values:
        nonlocal first
        if first:
            first = False
            raise RuntimeError("private executor exception")
        return await original(case, data)

    monkeypatch.setattr(runner, "execute_extraction", failing_once)
    report = await runner.run_evaluation(ROOT, url)
    assert report.error_cases == 1 and report.completed_cases == 19
    assert report.cases[0].error == "case_execution_failed"
    assert report.cases[0].assessments["service_severity"].status == "error"
    assert report.cases[-1].execution_status == "completed"
    assert "private executor exception" not in report.model_dump_json()
