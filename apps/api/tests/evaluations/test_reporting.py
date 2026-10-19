"""Artifact integrity, honest comparisons, and escaped standalone reports."""

import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from api.evaluations.contracts import load_case_set, observations
from api.evaluations.evidence import load_sources
from api.evaluations.judge_contracts import JudgeMethod
from api.evaluations.judge_prompt import digest
from api.evaluations.judging import FixtureJudge, judge_observations
from api.evaluations.report_comparison import (
    deterministic_changes,
    same_relevance_cohort,
    semantic_changes,
    semantic_comparison_limit,
)
from api.evaluations.report_inputs import ReportInputs, load_report_inputs
from api.evaluations.reporting import render_report
from api.evaluations.runner import ExecutionReport, execute_case
from api.evaluations.scoring import score_observations
from api.extraction.provider import ModelSettings, ProviderResult

ROOT = Path(__file__).resolve().parents[4]
DATA = load_case_set(ROOT / "knowledge/evaluations/workspace-v1.json")


@pytest.fixture(scope="module")
def execution() -> ExecutionReport:
    # Approval is explicitly unavailable without a database. The reporter must
    # preserve these executor errors rather than inventing a passing full run.
    cases = [asyncio.run(execute_case(c, DATA, ROOT, None)) for c in DATA.cases]
    sources = load_sources(ROOT, DATA, fixture_names=tuple(DATA.fixture_sources))
    return ExecutionReport(
        case_set_version=DATA.version,
        case_set_sha256=digest(
            (ROOT / "knowledge/evaluations/workspace-v1.json").read_bytes()
        ),
        specification_sha256=digest((ROOT / DATA.specification).read_bytes()),
        generated_at=datetime.now(UTC),
        code_revision="test-revision",
        dirty_worktree=True,
        corpus=[
            observations(
                dict(
                    document_id=s.metadata.document_id,
                    version=s.metadata.version,
                    content_hash=s.content_hash,
                    metadata_hash=s.metadata_hash,
                )
            )
            for s in sources
        ],
        configuration=observations(
            dict(
                provider="test-fixture",
                prompt_version="3",
                api_key="private-config-token",
            )
        ),
        completed_cases=sum(c.execution_status == "completed" for c in cases),
        error_cases=sum(c.execution_status == "error" for c in cases),
        cases=cases,
    )


class SyntheticJudge:
    def __init__(self, status: str = "pass"):
        self.status = status

    settings = ModelSettings("synthetic-judge-alias")

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        payload = json.loads(input_text)
        return ProviderResult(
            text=json.dumps(
                dict(
                    case_id=payload["case_id"],
                    verdicts=[
                        dict(
                            criterion=name,
                            status=self.status,
                            reason="Synthetic parsing test <script>alert(1)</script> | [link](https://invalid.test)",
                            references=["report"],
                        )
                        for name in payload["criteria"]
                    ],
                )
            ),
            resolved_model="synthetic-snapshot-v1",
        )


def artifacts(
    execution: ExecutionReport, method: JudgeMethod = "fixture"
) -> tuple[bytes, bytes, bytes]:
    raw = execution.model_dump_json().encode()
    metrics = score_observations(ROOT, raw).model_dump_json().encode()
    provider = FixtureJudge() if method == "fixture" else SyntheticJudge()
    judgments = (
        asyncio.run(judge_observations(ROOT, raw, provider, method=method))
        .model_dump_json()
        .encode()
    )
    return raw, metrics, judgments


def bundle(execution: ExecutionReport, method: JudgeMethod = "fixture") -> ReportInputs:
    return load_report_inputs(ROOT, *artifacts(execution, method))


def test_offline_report_preserves_denominators_errors_and_unmeasured(
    execution: ExecutionReport,
):
    inputs = bundle(execution)
    report = render_report(inputs)
    assert "Candidate mode: fixture" in report
    assert "No baseline supplied" in report and "were not assessed" in report
    assert "0 assessed" in report and "Unmeasured" in report and "Incomplete" in report
    assert "executor errors: 5" in report and "case\\_execution\\_failed" in report
    assert "semantic quality remains unmeasured" in report
    assert "Only S03 has relevance labels" in report
    assert "not recorded" in report and "private-config-token" not in report
    assert inputs.scores.observation_sha256 in report
    assert inputs.judge is not None and inputs.judge.rubric_sha256 in report


def test_missing_judgments_do_not_imply_quality(execution: ExecutionReport):
    raw, metrics, _ = artifacts(execution)
    inputs = load_report_inputs(ROOT, raw, metrics)
    assert "No judgment artifact supplied" in render_report(inputs)
    limit = semantic_comparison_limit(inputs, inputs)
    assert limit is not None and "judgments are missing" in limit


@pytest.mark.parametrize(
    "mutation",
    ["hash", "status", "counter", "summary", "missing", "duplicates", "retrieval"],
)
def test_altered_metrics_are_rejected(execution: ExecutionReport, mutation: str):
    raw, metrics, _ = artifacts(execution)
    value = json.loads(metrics)
    if mutation == "hash":
        value["observation_sha256"] = "0" * 64
    elif mutation == "status":
        value["cases"][0]["checks"][1]["status"] = "fail"
    elif mutation == "counter":
        value["failed_checks"] = 123
    elif mutation == "summary":
        value["summaries"][0]["passed"] = 123
    elif mutation == "missing":
        value["cases"].pop()
    elif mutation == "duplicates":
        value["cases"][-1] = value["cases"][0]
    else:
        value["retrieval"]["hit_rate_successful_cases"] = 0
    with pytest.raises(ValueError):
        load_report_inputs(ROOT, raw, json.dumps(value).encode())


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "input",
        "method",
        "attempts",
        "summary",
        "counter",
        "missing",
        "check",
        "fake_pass",
        "verdicts",
        "mechanical_reason",
    ],
)
def test_altered_judgments_are_rejected(execution: ExecutionReport, mutation: str):
    raw, metrics, judgments = artifacts(execution)
    value = json.loads(judgments)
    if mutation == "hash":
        value["observation_sha256"] = "0" * 64
    elif mutation == "input":
        value["cases"][0]["input_sha256"] = "0" * 64
    elif mutation == "method":
        value["cases"][0]["judging_method"] = "openai"
    elif mutation == "attempts":
        value["cases"][0]["attempts"] = 3
    elif mutation == "summary":
        value["summaries"][0]["passed"] = 50
    elif mutation == "counter":
        value["error_checks"] = 50
    elif mutation == "missing":
        value["cases"].pop()
    elif mutation == "check":
        value["cases"][0]["checks"].pop()
    elif mutation == "fake_pass":
        value["cases"][0]["checks"][0]["status"] = "pass"
    elif mutation == "mechanical_reason":
        value["cases"][0]["checks"][0]["reason"] = "private exception text"
    else:
        value["cases"][0]["verdicts"][0]["references"] = ["unknown.field"]
    with pytest.raises(ValueError):
        load_report_inputs(ROOT, raw, metrics, json.dumps(value).encode())


def test_same_artifacts_are_a_control_not_an_experiment(execution: ExecutionReport):
    inputs = bundle(execution)
    report = render_report(inputs, inputs)
    assert "comparison control, not a new candidate experiment" in report
    assert "No check status changes observed" in report
    assert "Fixture judgments do not support semantic quality comparisons" in report
    assert not deterministic_changes(inputs, inputs)


@pytest.mark.parametrize("direction", ["regression", "improvement", "assessment lost"])
def test_case_status_changes_are_not_hidden_in_averages(
    execution: ExecutionReport, direction: str
):
    modified = execution.model_copy(deep=True)
    assert modified.cases[0].observed is not None
    extraction = modified.cases[0].observed["extraction"]
    assert isinstance(extraction, dict)
    if direction == "assessment lost":
        modified.cases[0] = modified.cases[0].model_copy(
            update=dict(
                execution_status="error", observed=None, error="case_execution_failed"
            )
        )
    else:
        extraction["severity"] = "critical"
    original, changed = bundle(execution), bundle(modified)
    before, after = (
        (changed, original) if direction == "improvement" else (original, changed)
    )
    changes = deterministic_changes(before, after)
    assert any(c.case_id == "RF602-S01" and c.change == direction for c in changes)
    assert direction in render_report(after, before)


def test_failed_retrieval_cannot_raise_a_comparable_quality_average(
    execution: ExecutionReport,
):
    changed = execution.model_copy(deep=True)
    observed = next(c for c in changed.cases if c.case_id == "RF602-S03").observed
    assert observed is not None
    del observed["retrieval_result"]
    old, new = bundle(execution), bundle(changed)
    assert not same_relevance_cohort(old, new)
    report = render_report(new, old)
    assert "not comparable" in report and "uninspected" in report
    assert new.scores.retrieval["relevance_failed_cases"] == 1


@pytest.mark.parametrize(
    "mutation", ["settings", "rubric", "prompt", "unknown_model", "different_model"]
)
def test_semantic_comparison_requires_same_judge_protocol(
    execution: ExecutionReport, mutation: str
):
    raw, metrics, judgments = artifacts(execution, "openai")
    old = load_report_inputs(ROOT, raw, metrics, judgments)
    value = json.loads(judgments)
    if mutation == "settings":
        value["judge_settings"]["model"] = "different-alias"
    elif mutation == "rubric":
        value["rubric_sha256"] = "0" * 64
    elif mutation == "prompt":
        value["prompt_version"] = "changed"
    else:
        value["cases"][0]["resolved_model"] = (
            None if mutation == "unknown_model" else "different-snapshot"
        )
    new = load_report_inputs(ROOT, raw, metrics, json.dumps(value).encode())
    assert semantic_comparison_limit(old, new) is not None
    assert not semantic_changes(old, new)
    assert "Semantic comparison unavailable" in render_report(new, old)


def test_model_explanations_are_literal_and_semantic_comparison_can_run(
    execution: ExecutionReport,
):
    inputs = bundle(execution, "openai")
    assert semantic_comparison_limit(inputs, inputs) is None
    report = render_report(inputs, inputs)
    assert "<script>" not in report and "&lt;script&gt;" in report
    assert "[link](https://invalid.test)" not in report
    assert "\\[link\\]" in report
    assert "Human calibration has not been established" in report


def test_unknown_configuration_is_not_dumped_but_changes_are_visible(
    execution: ExecutionReport,
):
    old = bundle(execution)
    changed = execution.model_copy(deep=True)
    changed.configuration["api_key"] = "another-private-token"
    changed.configuration["prompt_version"] = "4"
    report = render_report(bundle(changed), old)
    assert "private-token" not in report and "private-config-token" not in report
    assert "Configuration SHA-256" in report
    assert "prompt\\_version | 3 | 4" in report


def test_offline_cli_writes_failures_protects_files_and_sanitizes_errors(
    execution: ExecutionReport, tmp_path: Path
):
    raw, metrics, judgments = artifacts(execution)
    paths = [
        tmp_path / name
        for name in ("observations.json", "metrics.json", "judgments.json")
    ]
    for path, content in zip(paths, (raw, metrics, judgments), strict=True):
        path.write_bytes(content)
    output = tmp_path / "report.md"
    command = [
        sys.executable,
        str(ROOT / "apps/api/scripts/report_workspace.py"),
        "--observations",
        str(paths[0]),
        "--metrics",
        str(paths[1]),
        "--judgments",
        str(paths[2]),
        "--output",
        str(output),
    ]
    environment = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "OPENAI_API_KEY",
            "DATABASE_URL",
            "TEST_DATABASE_URL",
            "EVALUATION_DATABASE_URL",
        )
    }
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert result.returncode == 1 and output.exists(), result.stderr
    original = output.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert output.read_bytes() == original
    malformed = tmp_path / "malformed.json"
    malformed.write_text("private malformed artifact")
    rejected = subprocess.run(
        command[: command.index("--output")]
        + [
            "--baseline-observations",
            str(malformed),
            "--baseline-metrics",
            str(paths[1]),
        ],
        capture_output=True,
        text=True,
    )
    assert (
        rejected.returncode == 2
        and not rejected.stdout
        and "private" not in rejected.stderr
    )
    missing_pair = subprocess.run(
        command[: command.index("--output")]
        + ["--baseline-observations", str(paths[0])],
        capture_output=True,
    )
    assert missing_pair.returncode == 2


def test_semantic_regressions_are_separate_from_deterministic_checks(
    execution: ExecutionReport,
):
    raw, metrics, old_judgments = artifacts(execution, "openai")
    new_judgments = asyncio.run(
        judge_observations(ROOT, raw, SyntheticJudge("fail"), method="openai")
    )
    before = load_report_inputs(ROOT, raw, metrics, old_judgments)
    after = load_report_inputs(
        ROOT, raw, metrics, new_judgments.model_dump_json().encode()
    )
    assert not deterministic_changes(before, after)
    changes = semantic_changes(before, after)
    assert len(changes) == 15 and all(c.change == "regression" for c in changes)
    assert "### Semantic changes" in render_report(after, before)
