"""RF-607 offline mechanics and synthetic decision-rule tests; no human labels."""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from api.evaluations.contracts import load_case_set
from api.evaluations.experiment import run_experiment
from api.evaluations.experiment_contracts import ExperimentReport, ExperimentReview
from api.evaluations.experiment_prompt import (
    ADDITION,
    BASELINE_SHA256,
    CANDIDATE_SHA256,
    CASE_IDS,
    prompts,
)
from api.evaluations.experiment_report import adoption, render_experiment
from api.evaluations.experiment_review import (
    load_experiment,
    load_review,
    review_template,
)
from api.evaluations.judge_prompt import digest
from api.extraction.prompts import EXTRACTION_PROMPT
from api.extraction.provider import (
    ModelSettings,
    ProviderError,
    ProviderFailureKind,
    ProviderResult,
    ProviderUsage,
)
from api.extraction.service import RetryPolicy

ROOT = Path(__file__).resolve().parents[4]
DATA = load_case_set(ROOT / "knowledge/evaluations/workspace-v1.json")


class TestProvider:
    __test__ = False
    settings = ModelSettings(
        "synthetic-model", max_output_tokens=2048, reasoning_effort="low"
    )

    def __init__(self, behavior: str = ""):
        self.behavior = behavior
        self.calls: list[tuple[str, str, type[BaseModel] | None]] = []

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        self.calls.append((instructions, input_text, output_schema))
        if self.behavior == "cancel":
            raise asyncio.CancelledError()
        if self.behavior == "provider":
            raise ProviderError(
                "private exception token", ProviderFailureKind.TRANSIENT
            )
        if self.behavior == "unexpected":
            raise RuntimeError("private exception token")
        if self.behavior == "refusal":
            return ProviderResult(refusal="private refusal")
        if self.behavior == "malformed":
            return ProviderResult(text="private invalid JSON")
        if self.behavior == "empty":
            return ProviderResult()
        if self.behavior == "invalid":
            return ProviderResult(text="{}")
        case = next(
            c
            for c in DATA.cases
            if c.case_id in CASE_IDS and c.input["report"] == input_text
        )
        fixture = case.setup["provider_response_fixture"]
        assert isinstance(fixture, str)
        payload = dict(DATA.provider_response_fixtures[fixture])
        if self.behavior == "regression" and ADDITION in instructions:
            payload["severity"] = "critical"
        return ProviderResult(
            text=json.dumps(payload),
            usage=ProviderUsage(10, 20, 30),
            resolved_model="synthetic-model-snapshot",
        )


def run(provider: TestProvider | None = None) -> ExperimentReport:
    return asyncio.run(run_experiment(ROOT, provider or TestProvider()))


@pytest.fixture(scope="module")
def experiment() -> ExperimentReport:
    return run()


def reviewed(report: ExperimentReport) -> ExperimentReview:
    raw = report.model_dump_json().encode()
    template = review_template(report, raw)
    return template.model_copy(
        update=dict(
            state="reviewed",
            reviewer="Kevin",
            reviewed_at=datetime.now(UTC),
            assessments=[
                a.model_copy(
                    update=dict(
                        status="pass",
                        reason="Synthetic decision-rule fixture, not a human calibration label.",
                    )
                )
                if a.status == "unmeasured"
                else a
                for a in template.assessments
            ],
        )
    )


def test_approved_pair_and_default_prompt_are_preserved(experiment: ExperimentReport):
    pair = prompts()
    assert (
        EXTRACTION_PROMPT.version == "3"
        and digest(EXTRACTION_PROMPT.instructions) == BASELINE_SHA256
    )
    assert digest(pair["candidate"].instructions) == CANDIDATE_SHA256
    provider = TestProvider()
    result = run(provider)
    assert len(provider.calls) == 12 and result.state == "completed"
    assert all(
        result.cases[i].input_report == result.cases[i + 1].input_report
        for i in range(0, 12, 2)
    )
    assert [c[0] for c in provider.calls] == [
        pair[v].instructions for _ in CASE_IDS for v in ("baseline", "candidate")
    ]
    assert all(
        c.attempts == 1
        and c.usage == dict(input_tokens=10, output_tokens=20, total_tokens=30)
        for c in result.cases
    )
    for c in result.cases:
        assert c.observed is not None
        call = c.observed["call"]
        assert (
            isinstance(call, dict) and call["prompt_version"] == pair[c.variant].version
        )
    assert not any(
        k.status in ("fail", "error") for c in result.cases for k in c.checks
    )
    assert all(s.mode == "fixture" for ss in result.summaries.values() for s in ss)
    assert load_experiment(ROOT, experiment.model_dump_json().encode()) == experiment


@pytest.mark.parametrize(
    "behavior", ["provider", "unexpected", "refusal", "malformed", "empty", "invalid"]
)
def test_failures_are_retained_without_retry_or_raw_text(behavior: str):
    provider = TestProvider(behavior)
    result = run(provider)
    assert len(provider.calls) == 12 and all(
        c.status == "error" and c.attempts == 1 for c in result.cases
    )
    assert "private" not in result.model_dump_json()
    assert all(k.status == "error" for c in result.cases for k in c.semantic_checks)
    assert all(
        k.status == "error"
        for c in result.cases
        for k in c.checks
        if k.name != "output_schema"
    )
    assert load_experiment(ROOT, result.model_dump_json().encode()) == result


def test_cancellation_retains_progress_and_never_resumes():
    progress: list[ExperimentReport] = []
    provider = TestProvider("cancel")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            run_experiment(
                ROOT,
                provider,
                progress=lambda r: progress.append(r.model_copy(deep=True)),
            )
        )
    assert len(provider.calls) == 1
    saved = progress[-1]
    assert saved.state == "cancelled" and saved.cases[0].error == "cancelled"
    assert sum(c.status == "pending" for c in saved.cases) == 11
    assert load_experiment(ROOT, saved.model_dump_json().encode()) == saved


def test_approved_timeout_is_passed_to_service(monkeypatch: pytest.MonkeyPatch):
    from api.evaluations import experiment as module

    original = module.extract_issue_report
    policies: list[RetryPolicy] = []

    from api.extraction.prompts import PromptSpec
    from api.extraction.provider import LLMProvider

    async def inspect(
        report: str,
        provider: LLMProvider,
        retry_policy: RetryPolicy,
        *,
        prompt: PromptSpec,
    ):
        policies.append(retry_policy)
        return await original(report, provider, retry_policy, prompt=prompt)

    monkeypatch.setattr(module, "extract_issue_report", inspect)
    run()
    assert len(policies) == 12 and all(
        p.max_attempts == 1 and p.timeout_seconds == 60 for p in policies
    )


def test_checkpoint_write_failure_stops_before_next_paid_call():
    provider = TestProvider()

    def broken(report: ExperimentReport):
        if any(c.status == "completed" for c in report.cases):
            raise OSError("full disk")

    with pytest.raises(OSError):
        asyncio.run(run_experiment(ROOT, provider, progress=broken))
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    "mutation",
    ["prompt", "case", "label", "cohort", "counter", "summary", "usage", "policy"],
)
def test_saved_artifact_consistency(experiment: ExperimentReport, mutation: str):
    raw = json.loads(experiment.model_dump_json())
    if mutation == "prompt":
        raw["candidate"]["sha256"] = "0" * 64
    elif mutation == "case":
        raw["cases"][0]["input_report"] = "changed"
    elif mutation == "label":
        raw["cases"][0]["expected"]["severity_allowed"] = ["critical"]
    elif mutation == "cohort":
        raw["cases"].pop()
    elif mutation == "counter":
        raw["cases"][0]["attempts"] = 2
    elif mutation == "summary":
        raw["summaries"]["baseline"][0]["passed"] = 999
    elif mutation == "usage":
        raw["cases"][0]["usage"]["total_tokens"] = 999
    else:
        raw["cases"][0]["observed"]["clarification"]["needs_clarification"] = True
    with pytest.raises(ValueError):
        load_experiment(ROOT, json.dumps(raw).encode())


def test_review_starts_unmeasured_and_cannot_certify_fixture(
    experiment: ExperimentReport,
):
    raw = experiment.model_dump_json().encode()
    review = review_template(experiment, raw)
    assert review.state == "draft" and review.reviewer is None
    assert len(review.assessments) == 36 and all(
        a.status in ("unmeasured", "not_applicable") for a in review.assessments
    )
    assert load_review(experiment, raw, review.model_dump_json().encode()) == review
    assert "fixture outputs cannot establish model improvement" in adoption(
        experiment, reviewed(experiment)
    )
    assert "<script>" not in render_experiment(experiment, review)


@pytest.mark.parametrize(
    "mutation", ["hash", "reviewer", "missing", "duplicate", "na_override"]
)
def test_review_cannot_change_cohorts_or_unavailable_slots(
    experiment: ExperimentReport, mutation: str
):
    raw = experiment.model_dump_json().encode()
    value = json.loads(review_template(experiment, raw).model_dump_json())
    if mutation == "hash":
        value["experiment_sha256"] = "0" * 64
    elif mutation == "reviewer":
        value["state"] = "reviewed"
    elif mutation == "missing":
        value["assessments"].pop()
    elif mutation == "duplicate":
        value["assessments"][-1] = value["assessments"][0]
    else:
        next(a for a in value["assessments"] if a["status"] == "not_applicable")[
            "status"
        ] = "pass"
    with pytest.raises(ValueError):
        load_review(experiment, raw, json.dumps(value).encode())


@pytest.mark.parametrize(
    "scenario",
    [
        "pending",
        "unchanged",
        "better",
        "worse",
        "unknown_model",
        "failed_call",
        "deterministic_regression",
        "regression_with_pending_review",
    ],
)
def test_predeclared_decision_rule_with_synthetic_judgments(
    experiment: ExperimentReport, scenario: str
):
    # A synthetic live label exercises only interpretation; no network or human judgment.
    report = experiment.model_copy(deep=True, update=dict(mode="live"))
    review = reviewed(report)
    if scenario == "pending":
        review = review_template(report, report.model_dump_json().encode())
    elif scenario in ("better", "worse"):
        target = next(
            a
            for a in review.assessments
            if a.variant == ("baseline" if scenario == "better" else "candidate")
            and a.criterion == "factual_fidelity"
        )
        review = review.model_copy(
            update=dict(
                assessments=[
                    a.model_copy(update=dict(status="fail")) if a == target else a
                    for a in review.assessments
                ]
            )
        )
    elif scenario == "unknown_model":
        report.cases[0] = report.cases[0].model_copy(update=dict(resolved_model=None))
    elif scenario == "failed_call":
        report.cases[0] = report.cases[0].model_copy(update=dict(status="error"))
    elif scenario in ("deterministic_regression", "regression_with_pending_review"):
        if scenario == "regression_with_pending_review":
            review = review_template(report, report.model_dump_json().encode())
        c = report.cases[1]
        report.cases[1] = c.model_copy(
            update=dict(
                checks=[
                    k.model_copy(update=dict(status="fail"))
                    if k.name == "severity_allowed"
                    else k
                    for k in c.checks
                ]
            )
        )
    result = adoption(report, review)
    expected = {
        "pending": "Pending Kevin",
        "unchanged": "No comparable semantic improvement",
        "better": "supports adopting",
        "worse": "semantic criterion regressed",
        "unknown_model": "versions differ or are unavailable",
        "failed_call": "failed extractions",
        "deterministic_regression": "deterministic check regressed",
        "regression_with_pending_review": "deterministic check regressed",
    }
    assert expected[scenario] in result


def test_invalid_settings_prevent_any_call():
    provider = TestProvider()
    provider.settings = replace(provider.settings, max_output_tokens=4096)
    with pytest.raises(ValueError):
        run(provider)
    assert not provider.calls


def test_offline_review_cli_and_live_command_guard(
    experiment: ExperimentReport, tmp_path: Path
):
    artifact = tmp_path / "experiment.json"
    artifact.write_text(experiment.model_dump_json())
    output = tmp_path / "comparison.md"
    template = tmp_path / "review.json"
    command = [
        sys.executable,
        str(ROOT / "apps/api/scripts/review_experiment.py"),
        "--input",
        str(artifact),
        "--output",
        str(output),
        "--review-template",
        str(template),
    ]
    environment = {
        k: v
        for k, v in os.environ.items()
        if k
        not in ("OPENAI_API_KEY", "OPENAI_MODEL", "DATABASE_URL", "TEST_DATABASE_URL")
    }
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    original = output.read_bytes()
    assert (
        subprocess.run(command, capture_output=True).returncode == 2
        and output.read_bytes() == original
    )
    rejected = subprocess.run(
        [
            sys.executable,
            str(ROOT / "apps/api/scripts/experiment_extraction.py"),
            "--output-dir",
            str(tmp_path / "never-created"),
        ],
        env=environment,
        capture_output=True,
    )
    assert rejected.returncode == 2 and not (tmp_path / "never-created").exists()
