"""RF-605 mechanics only: synthetic verdicts are not human calibration labels."""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel

from api.evaluations.contracts import load_case_set, observations
from api.evaluations.evidence import load_sources
from api.evaluations.judge_contracts import JudgeMethod, JudgeOutput
from api.evaluations.judge_prompt import INSTRUCTIONS, RUBRIC_TEXT, digest
from api.evaluations.judging import FixtureJudge, judge_input, judge_observations
from api.evaluations.runner import ExecutionReport, execute_case
from api.extraction.provider import ModelSettings, ProviderResult, ProviderUsage

ROOT = Path(__file__).resolve().parents[4]
DATA = load_case_set(ROOT / "knowledge/evaluations/workspace-v1.json")


@pytest.fixture(scope="module")
def report() -> ExecutionReport:
    # The six relevant observations use real offline extraction. Approval cases
    # explicitly lack a database; all frozen identities/provenance stay present.
    results = [asyncio.run(execute_case(c, DATA, ROOT, None)) for c in DATA.cases]
    sources = load_sources(ROOT, DATA, fixture_names=tuple(DATA.fixture_sources))
    from datetime import UTC, datetime

    return ExecutionReport(
        case_set_version=DATA.version,
        case_set_sha256=digest(
            (ROOT / "knowledge/evaluations/workspace-v1.json").read_bytes()
        ),
        specification_sha256=digest((ROOT / DATA.specification).read_bytes()),
        generated_at=datetime.now(UTC),
        code_revision=None,
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
        configuration=observations(dict(provider="test-fixture", live_calls=False)),
        completed_cases=sum(r.execution_status == "completed" for r in results),
        error_cases=sum(r.execution_status == "error" for r in results),
        cases=results,
    )


class StubJudge:
    settings = ModelSettings("synthetic-judge-alias", max_output_tokens=2048)

    def __init__(self, mutation: str = ""):
        self.mutation = mutation
        self.calls: list[tuple[str, str, type[BaseModel] | None]] = []

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        self.calls.append((instructions, input_text, output_schema))
        if self.mutation == "timeout":
            await asyncio.Event().wait()
        if self.mutation == "cancel":
            raise asyncio.CancelledError()
        if self.mutation == "provider":
            raise RuntimeError("private provider credentials must not appear")
        if self.mutation == "refusal":
            return ProviderResult(refusal="private refusal must not appear")
        if self.mutation == "empty":
            return ProviderResult()
        if self.mutation == "malformed":
            return ProviderResult(text="private invalid JSON")
        value = json.loads(input_text)
        verdicts = [
            dict(
                criterion=c,
                status="pass",
                reason="Synthetic parsing test verdict.",
                references=["report", "extraction.summary"],
            )
            for c in value["criteria"]
        ]
        response = dict(case_id=value["case_id"], verdicts=verdicts)
        if self.mutation == "duplicate":
            verdicts[-1] = verdicts[0]
        elif self.mutation == "missing":
            verdicts.pop()
        elif self.mutation == "unknown":
            verdicts[0]["criterion"] = "overall_quality"
        elif self.mutation == "status":
            verdicts[0]["status"] = "not_applicable"
        elif self.mutation == "reason":
            verdicts[0]["reason"] = "   "
        elif self.mutation == "references":
            verdicts[0]["references"] = ["private.unsupplied_source"]
        elif self.mutation == "no_references":
            verdicts[0]["references"] = []
        elif self.mutation == "identity":
            response["case_id"] = "unknown-case"
        elif self.mutation == "extra":
            response["tool_call"] = "create_ticket"
        elif self.mutation in ("fail", "unmeasured"):
            verdicts[0]["status"] = self.mutation
        return ProviderResult(
            text=json.dumps(response),
            usage=ProviderUsage(10, 20, 30),
            resolved_model="synthetic-judge-snapshot-v1",
        )


def score(report: ExecutionReport, judge: StubJudge, method: JudgeMethod = "fixture"):
    return asyncio.run(
        judge_observations(
            ROOT,
            report.model_dump_json().encode(),
            judge,
            method=method,
            timeout_seconds=0.1,
        )
    )


def test_offline_fixture_never_claims_measured_quality(report: ExecutionReport):
    result = asyncio.run(
        judge_observations(ROOT, report.model_dump_json().encode(), FixtureJudge())
    )
    assert len(result.cases) == 6
    assert not result.semantic_quality_measured and not result.assessment_complete
    assert result.failed_checks == result.error_checks == 0
    assert result.unmeasured_checks >= 12
    assert all(c.attempts == 1 and c.resolved_model is None for c in result.cases)
    assert all(s.judging_method == "fixture" for s in result.summaries)
    assert all(s.pass_rate_assessed_checks is None for s in result.summaries)


def test_synthetic_positive_verdict_does_not_certify_fixture(report: ExecutionReport):
    result = score(report, StubJudge())
    assert not result.semantic_quality_measured
    assert all(c.status != "pass" for case in result.cases for c in case.checks)
    assert all(v.status == "pass" for case in result.cases for v in case.verdicts)


@pytest.mark.parametrize("verdict", ["", "fail", "unmeasured"])
def test_model_judgment_reporting_without_network(
    report: ExecutionReport, verdict: str
):
    provider = StubJudge(verdict)
    result = score(report, provider, "openai")
    assert result.candidate_mode == "fixture" and result.judging_method == "openai"
    assert result.semantic_quality_measured
    assert result.assessment_complete == (verdict != "unmeasured")
    assert result.failed_checks == (6 if verdict == "fail" else 0)
    assert result.unmeasured_checks == (6 if verdict == "unmeasured" else 0)
    assert result.rubric_sha256 == digest(RUBRIC_TEXT)
    assert result.prompt_sha256 == digest(INSTRUCTIONS)
    assert result.judge_settings["model"] == "synthetic-judge-alias"
    assert result.max_attempts == 1
    assert all(c.resolved_model == "synthetic-judge-snapshot-v1" for c in result.cases)
    assert all(
        c.usage == dict(input_tokens=10, output_tokens=20, total_tokens=30)
        for c in result.cases
    )
    assert len(provider.calls) == 6
    assert all(c[0] == INSTRUCTIONS and c[2] is JudgeOutput for c in provider.calls)
    # The original forged instruction is preserved as data, never instructions.
    attack = json.loads(provider.calls[-1][1])
    assert "SYSTEM:" in attack["report"] and "SYSTEM:" not in provider.calls[-1][0]
    assert "expected" not in attack and "assessments" not in attack


@pytest.mark.parametrize(
    "mutation",
    [
        "timeout",
        "provider",
        "refusal",
        "empty",
        "malformed",
        "duplicate",
        "missing",
        "unknown",
        "status",
        "reason",
        "references",
        "no_references",
        "identity",
        "extra",
    ],
)
def test_invalid_judge_responses_are_safe_bounded_errors(
    report: ExecutionReport, mutation: str
):
    provider = StubJudge(mutation)
    result = score(report, provider, "openai")
    assert result.error_checks >= 12 and not result.assessment_complete
    assert not result.semantic_quality_measured and result.failed_checks == 0
    assert len(provider.calls) == 6 and all(c.attempts == 1 for c in result.cases)
    assert "private" not in result.model_dump_json()
    assert all(not c.verdicts and c.error for c in result.cases)


@pytest.mark.parametrize("mutation", ["execution", "extraction", "questions"])
def test_missing_observations_never_turn_into_not_applicable(
    report: ExecutionReport, mutation: str
):
    clone = report.model_copy(deep=True)
    first = clone.cases[0]
    assert first.observed is not None
    if mutation == "execution":
        clone.cases[0] = first.model_copy(
            update={"execution_status": "error", "observed": None}
        )
    elif mutation == "extraction":
        del first.observed["extraction"]
    else:
        first.observed["clarification"] = {}
    provider = StubJudge()
    result = score(clone, provider, "openai")
    assert result.cases[0].attempts == 0
    assert all(c.status == "error" for c in result.cases[0].checks)
    assert len(provider.calls) == 5 and result.error_checks == 3


def test_empty_selected_questions_are_not_judged(report: ExecutionReport):
    case = DATA.cases[0]
    raw, criteria, fields = judge_input(case, report.cases[0])
    assert json.loads(raw)["selected_questions"] == []
    assert "question_relevance" not in criteria
    assert "selected_questions" in fields
    result = score(report, StubJudge(), "openai")
    assert result.cases[0].checks[-1].status == "not_applicable"
    assert len(result.cases[0].verdicts) == 2


@pytest.mark.parametrize(
    "mutation", ["hash", "labels", "boolean_label", "missing_case", "corpus", "spec"]
)
def test_provenance_is_checked_before_provider_calls(
    report: ExecutionReport, mutation: str
):
    clone = report.model_copy(deep=True)
    if mutation == "hash":
        clone = clone.model_copy(update={"case_set_sha256": "0" * 64})
    elif mutation == "labels":
        clone.cases[0].expected["severity_allowed"] = ["critical"]
    elif mutation == "boolean_label":
        counts = clone.cases[0].expected["question_count"]
        assert isinstance(counts, dict)
        counts["min"] = False
    elif mutation == "missing_case":
        clone.cases.pop()
    elif mutation == "corpus":
        clone.corpus.clear()
    else:
        clone = clone.model_copy(update={"specification_sha256": "0" * 64})
    provider = StubJudge()
    with pytest.raises(ValueError):
        score(clone, provider)
    assert not provider.calls


def test_cancellation_propagates(report: ExecutionReport):
    provider = StubJudge("cancel")
    with pytest.raises(asyncio.CancelledError):
        score(report, provider)
    assert len(provider.calls) == 1


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_timeout_must_be_positive_and_finite(report: ExecutionReport, timeout: float):
    provider = StubJudge()
    with pytest.raises(ValueError):
        asyncio.run(
            judge_observations(
                ROOT,
                report.model_dump_json().encode(),
                provider,
                timeout_seconds=timeout,
            )
        )
    assert not provider.calls


def test_judge_cli_is_offline_and_protects_reports(
    report: ExecutionReport, tmp_path: Path
):
    input_path = tmp_path / "observations.json"
    input_path.write_text(report.model_dump_json())
    output = tmp_path / "judgments.json"
    command = [
        sys.executable,
        str(ROOT / "apps/api/scripts/judge_workspace.py"),
        "--input",
        str(input_path),
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
    run = subprocess.run(command, capture_output=True, text=True, env=environment)
    assert run.returncode == 0, run.stderr
    original = output.read_bytes()
    assert not json.loads(original)["semantic_quality_measured"]
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert output.read_bytes() == original
    # Supplying a model alone is not permission for network access.
    rejected = subprocess.run(
        command[:-2] + ["--judge", "openai", "--model", "never-called"],
        capture_output=True,
        env=environment,
    )
    assert rejected.returncode == 2 and not rejected.stdout


def test_judge_model_cannot_be_empty(report: ExecutionReport):
    provider = StubJudge()
    provider.settings = replace(provider.settings, model=" ")
    with pytest.raises(ValueError):
        score(report, provider)


def test_unknown_method_is_rejected(report: ExecutionReport):
    with pytest.raises(ValueError):
        score(report, StubJudge(), cast(JudgeMethod, "unknown"))
