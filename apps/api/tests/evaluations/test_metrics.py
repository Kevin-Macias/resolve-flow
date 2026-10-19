"""Metric arithmetic, observed regressions, provenance, and real fixture scoring."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from api.evaluations.contracts import Values, load_case_set
from api.evaluations.metric_contracts import Check, ScoredCase
from api.evaluations.metrics import score_case, summarize
from api.evaluations.runner import ExecutionReport, execute_case, run_evaluation
from api.evaluations.scoring import score_observations

ROOT = Path(__file__).resolve().parents[4]
DATA = load_case_set(ROOT / "knowledge/evaluations/workspace-v1.json")


@pytest.fixture(scope="module")
def full_report() -> ExecutionReport:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for complete scoring integration")
    return asyncio.run(run_evaluation(ROOT, url))


def changed(report: ExecutionReport, cid: str) -> tuple[ExecutionReport, Values]:
    clone = report.model_copy(deep=True)
    observed = next(c for c in clone.cases if c.case_id == cid).observed
    assert observed is not None
    return clone, observed


def checks_for(report: ExecutionReport, cid: str) -> dict[str, Check]:
    scored = score_observations(ROOT, report.model_dump_json().encode())
    return {
        check.name: check
        for case in scored.cases
        if case.case_id == cid
        for check in case.checks
    }


def test_summary_denominators_and_incompleteness():
    cases = [
        ScoredCase(
            case_id=f"case-{status}",
            group="ambiguous",
            target="extraction",
            checks=[
                Check(
                    name="check",
                    dimension="structure",
                    status=status,
                    reason="fixture arithmetic",
                )
            ],
        )
        for status in ("pass", "fail", "error", "unmeasured", "not_applicable")
    ]
    result = summarize(cases)[0]
    assert result.assessed_checks == 2 and result.total_checks == 5
    assert result.pass_rate_assessed_checks == 0.5 and result.incomplete
    for status in ("error", "unmeasured", "not_applicable"):
        subset = cases[0].model_copy(
            update={
                "checks": [
                    Check(
                        name="check",
                        dimension="structure",
                        status=status,
                        reason="fixture arithmetic",
                    )
                ]
            }
        )
        summary = summarize([subset])[0]
        assert (
            summary.pass_rate_assessed_checks is None and summary.assessed_checks == 0
        )
        assert summary.incomplete == (status != "not_applicable")


def test_fixture_execution_has_no_deterministic_mismatches_but_semantics_unmeasured(
    full_report: ExecutionReport,
):
    result = score_observations(ROOT, full_report.model_dump_json().encode())
    assert result.failed_checks == 0 and result.error_checks == 0, (
        result.model_dump_json()
    )
    assert result.unmeasured_checks == 6 and not result.assessment_complete
    assert not result.semantic_quality_measured
    assert result.retrieval["hit_rate_successful_cases"] == 1
    assert result.retrieval["mean_reciprocal_rank_successful_cases"] == 1
    assert result.retrieval["mean_listed_section_coverage_successful_cases"] == 0.5
    assert result.retrieval["relevance_successful_cases"] == 1
    assert len(result.cases) == 20


@pytest.mark.parametrize(
    ("cid", "field", "wrong", "name"),
    [
        ("RF602-S01", "service_code", None, "service_allowed"),
        ("RF602-S01", "severity", "critical", "severity_allowed"),
        ("RF602-M01", "severity", "low", "severity_allowed"),
        ("RF602-M02", "service_code", "issue-reports", "service_allowed"),
    ],
)
def test_classification_regressions_without_database(
    cid: str, field: str, wrong: str | None, name: str
):
    case = next(c for c in DATA.cases if c.case_id == cid)
    result = asyncio.run(execute_case(case, DATA, ROOT, None))
    assert result.observed
    extraction = result.observed["extraction"]
    assert isinstance(extraction, dict)
    extraction[field] = wrong
    scored = score_case(case, result, DATA, ROOT)
    assert next(c for c in scored.checks if c.name == name).status == "fail"
    assert (
        next(c for c in scored.checks if c.dimension == "facts").status == "unmeasured"
    )


@pytest.mark.parametrize(
    "mutation",
    ["missing_questions", "too_many_questions", "missing_reason", "bad_extraction"],
)
def test_missing_and_wrong_extraction_observations(
    full_report: ExecutionReport, mutation: str
):
    report, observed = changed(full_report, "RF602-M03")
    clarification = observed["clarification"]
    assert isinstance(clarification, dict)
    if mutation == "missing_questions":
        del clarification["questions"]
    elif mutation == "too_many_questions":
        clarification["questions"] = ["a", "b", "c"]
    elif mutation == "missing_reason":
        clarification["reasons"] = []
    else:
        observed["extraction"] = {}
    checks = checks_for(report, "RF602-M03")
    expected = {
        "missing_questions": ("question_count", "error"),
        "too_many_questions": ("question_count", "fail"),
        "missing_reason": ("required_reasons", "fail"),
        "bad_extraction": ("output_schema", "fail"),
    }
    name, status = expected[mutation]
    assert checks[name].status == status


@pytest.mark.parametrize(
    "mutation", ["wrong_order", "missing_turns", "third_round", "bad_pause"]
)
def test_clarification_regressions(full_report: ExecutionReport, mutation: str):
    report, observed = changed(full_report, "RF602-M05")
    if mutation == "wrong_order":
        turns = observed["accepted_turns"]
        assert isinstance(turns, list)
        observed["accepted_turns"] = list(reversed(turns))
    elif mutation == "missing_turns":
        del observed["accepted_turns"]
    elif mutation == "third_round":
        observed["answered_rounds"] = 3
    else:
        pauses = observed["pauses"]
        assert isinstance(pauses, list)
        pauses[-1] = {
            "mode": "answer_or_continue",
            "cause": "questions_available",
            "questions": ["Third question?"],
        }
    checks = checks_for(report, "RF602-M05")
    name = {
        "wrong_order": "accepted_answers_in_order",
        "missing_turns": "accepted_answers_in_order",
        "third_round": "answered_rounds",
        "bad_pause": "final_pause",
    }[mutation]
    assert checks[name].status == ("error" if mutation == "missing_turns" else "fail")


@pytest.mark.parametrize(
    "mutation",
    ["decision_binding", "retry", "duplicate", "first_decision", "missing_snapshot"],
)
def test_approval_regressions(full_report: ExecutionReport, mutation: str):
    report, observed = changed(full_report, "RF602-S04")
    if mutation == "decision_binding":
        receipt = observed["decision_receipt"]
        assert isinstance(receipt, dict)
        receipt["fingerprint"] = "f" * 64
    elif mutation == "retry":
        observed["tool_dispatches"] = 2
    elif mutation == "duplicate":
        observed["outcomes"] = [None, None]
    elif mutation == "first_decision":
        observed["saved_decision"] = "reject"
    else:
        del observed["proposal_snapshots"]
    checks = checks_for(report, "RF602-S04")
    name = {
        "decision_binding": "exact_saved_binding",
        "retry": "tool_dispatches",
        "duplicate": "duplicate_result",
        "first_decision": "exact_saved_binding",
        "missing_snapshot": "exact_saved_binding",
    }[mutation]
    assert checks[name].status == (
        "error" if mutation == "missing_snapshot" else "fail"
    )


@pytest.mark.parametrize(
    "mutation", ["empty", "duplicate", "foreign", "bad_excerpt", "missing", "bad_rank"]
)
def test_retrieval_and_citation_regressions(
    full_report: ExecutionReport, mutation: str
):
    report, observed = changed(full_report, "RF602-S03")
    raw = observed["retrieval_result"]
    assert isinstance(raw, dict)
    items = raw["evidence"]
    assert isinstance(items, list)
    first = items[0]
    assert isinstance(first, dict)
    if mutation == "empty":
        raw["evidence"] = []
    elif mutation == "duplicate":
        duplicate = dict(first)
        duplicate["rank"] = 2
        raw["evidence"] = [first, duplicate]
    elif mutation == "foreign":
        metadata = first["metadata"]
        assert isinstance(metadata, dict)
        metadata["access_class"] = "CUSTOMER_ACCOUNT"
        metadata["customer_account_id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        first["text"] = "secret foreign passage must never appear in the metrics report"
    elif mutation == "bad_excerpt":
        first["text"] = "fabricated quotation"
    elif mutation == "missing":
        del observed["retrieval_result"]
    else:
        first["rank"] = 9
    result = score_observations(ROOT, report.model_dump_json().encode())
    checks = {
        c.name: c
        for case in result.cases
        if case.case_id == "RF602-S03"
        for c in case.checks
    }
    expected = {
        "empty": ("hit_at_5", "fail"),
        "duplicate": ("duplicate_chunks", "fail"),
        "foreign": ("exclusion_violations", "fail"),
        "bad_excerpt": ("citation_integrity", "fail"),
        "missing": ("retrieval_schema", "error"),
        "bad_rank": ("retrieval_schema", "fail"),
    }
    name, status = expected[mutation]
    assert checks[name].status == status
    if mutation == "empty":
        assert result.retrieval["mean_reciprocal_rank_successful_cases"] == 0
        assert result.retrieval["relevance_successful_cases"] == 1
    else:
        assert result.retrieval["mean_reciprocal_rank_successful_cases"] is None
        assert result.retrieval["relevance_failed_cases"] == 1
    if mutation == "missing":
        assert result.retrieval["uninspected_cases"] == 1
    assert "secret foreign passage" not in result.model_dump_json()
    assert "fabricated quotation" not in result.model_dump_json()


@pytest.mark.parametrize(
    "mutation",
    ["duplicate_case", "missing_case", "expected_label", "hash", "source_snapshot"],
)
def test_report_provenance_before_scoring(full_report: ExecutionReport, mutation: str):
    raw: dict[str, Any] = full_report.model_dump(mode="json")
    if mutation == "duplicate_case":
        raw["cases"][0] = raw["cases"][1]
    elif mutation == "missing_case":
        raw["cases"].pop()
    elif mutation == "expected_label":
        raw["cases"][0]["expected"]["severity_allowed"] = ["critical"]
    elif mutation == "hash":
        raw["case_set_sha256"] = "f" * 64
    else:
        raw["corpus"][0]["content_hash"] = "f" * 64
    with pytest.raises(ValueError):
        score_observations(ROOT, json.dumps(raw).encode())


def test_executor_errors_do_not_raise_the_success_rate(full_report: ExecutionReport):
    report = full_report.model_copy(deep=True)
    report.cases[0] = report.cases[0].model_copy(
        update={
            "execution_status": "error",
            "observed": None,
            "error": "case_execution_failed",
        }
    )
    scored = score_observations(ROOT, report.model_dump_json().encode())
    assert scored.error_checks > 0 and not scored.assessment_complete
    groups = [
        s
        for s in scored.summaries
        if s.target == "extraction"
        and s.group == "straightforward"
        and s.dimension == "service_severity"
    ]
    assert len(groups) == 2
    assert all(
        group.errors == 1
        and group.passed == 1
        and group.assessed_checks == 1
        and group.incomplete
        for group in groups
    )


def test_boolean_does_not_pass_as_integer_count(full_report: ExecutionReport):
    report, observed = changed(full_report, "RF602-S04")
    observed["tool_dispatches"] = True
    assert checks_for(report, "RF602-S04")["tool_dispatches"].status == "fail"


def test_scoring_cli_is_offline_and_preserves_output_file(
    full_report: ExecutionReport, tmp_path: Path
):
    input_path = tmp_path / "observations.json"
    input_path.write_text(full_report.model_dump_json())
    output_path = tmp_path / "metrics.json"
    command = [
        sys.executable,
        str(ROOT / "apps/api/scripts/score_workspace.py"),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
    ]
    environment = os.environ.copy()
    for name in (
        "DATABASE_URL",
        "EVALUATION_DATABASE_URL",
        "TEST_DATABASE_URL",
        "OPENAI_API_KEY",
    ):
        environment.pop(name, None)
    completed = subprocess.run(command, text=True, capture_output=True, env=environment)
    assert completed.returncode == 0, completed.stderr
    original = output_path.read_bytes()
    assert json.loads(original)["semantic_quality_measured"] is False
    repeated = subprocess.run(command, text=True, capture_output=True)
    assert repeated.returncode == 2 and output_path.read_bytes() == original
    malformed = tmp_path / "invalid.json"
    malformed.write_text("{bad json with private data")
    rejected = subprocess.run(
        [
            sys.executable,
            str(ROOT / "apps/api/scripts/score_workspace.py"),
            "--input",
            str(malformed),
        ],
        text=True,
        capture_output=True,
    )
    assert (
        rejected.returncode == 2
        and not rejected.stdout
        and "private data" not in rejected.stderr
    )


def test_service_and_severity_have_separate_aggregate_scores(
    full_report: ExecutionReport,
):
    report, observed = changed(full_report, "RF602-S01")
    extraction = observed["extraction"]
    assert isinstance(extraction, dict)
    extraction["severity"] = "critical"
    scored = score_observations(ROOT, report.model_dump_json().encode())
    summaries = {
        s.metric: s
        for s in scored.summaries
        if s.target == "extraction"
        and s.group == "straightforward"
        and s.dimension == "service_severity"
    }
    assert summaries["service_allowed"].pass_rate_assessed_checks == 1
    assert summaries["severity_allowed"].pass_rate_assessed_checks == 0.5
