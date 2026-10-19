"""Bind retained scores and judgments to their original observation bytes."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from api.evaluations.contracts import load_case_set
from api.evaluations.judge_contracts import JudgeReport, JudgeSummary
from api.evaluations.judge_prompt import digest
from api.evaluations.judging import judge_input
from api.evaluations.metric_contracts import ScoredCase
from api.evaluations.metrics import summarize
from api.evaluations.runner import ExecutionReport
from api.evaluations.scoring import ScoringReport, score_observations


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class ReportInputs:
    execution: ExecutionReport
    scores: ScoringReport
    judge: JudgeReport | None
    scores_sha256: str
    judge_sha256: str | None


def validate_judge(
    root: Path, execution: ExecutionReport, scores: ScoringReport, raw: bytes
) -> JudgeReport:
    judge = JudgeReport.model_validate_json(raw, strict=True)
    for field in (
        "case_set_version",
        "case_set_sha256",
        "specification_sha256",
        "observation_sha256",
    ):
        if getattr(judge, field) != getattr(scores, field):
            raise ValueError("Judgments do not belong to these observations")
    if (
        judge.candidate_mode != execution.mode
        or not math.isfinite(judge.timeout_seconds)
        or judge.timeout_seconds <= 0
        or judge.judge_provider
        != ("offline_fixture" if judge.judging_method == "fixture" else "openai")
        or not isinstance(judge.judge_settings.get("model"), str)
        or not str(judge.judge_settings["model"]).strip()
    ):
        raise ValueError("Invalid judge configuration")
    data = load_case_set(root / "knowledge/evaluations/workspace-v1.json")
    definitions = {
        c.case_id: c
        for c in data.cases
        if c.target == "extraction" and c.semantic_review
    }
    if len(judge.cases) != len(definitions) or {c.case_id for c in judge.cases} != set(
        definitions
    ):
        raise ValueError("Invalid judge case coverage")
    observed = {c.case_id: c for c in execution.cases}
    all_criteria = {"factual_fidelity", "uncertainty_attribution", "question_relevance"}
    for case in judge.cases:
        if (
            case.group != definitions[case.case_id].group
            or case.judging_method != judge.judging_method
        ):
            raise ValueError("Invalid judge case identity")
        try:
            text, criteria, fields = judge_input(
                definitions[case.case_id], observed[case.case_id]
            )
        except (ValueError, KeyError, TypeError):
            if (
                case.input_sha256 is not None
                or case.error != "missing_observations"
                or case.attempts != 0
            ):
                raise ValueError("Invalid missing-observation assessment") from None
            criteria = list(all_criteria)
            fields: set[str] = set()
        else:
            if (
                case.input_sha256 != digest(text)
                or case.attempts != 1
                or case.error == "missing_observations"
            ):
                raise ValueError("Judge input or attempt mismatch")
        if case.candidate_mode != execution.mode:
            raise ValueError("Judge candidate mode mismatch")
        verdicts = {v.criterion: v for v in case.verdicts}
        if case.error:
            if case.verdicts:
                raise ValueError("Error case contains verdicts")
        elif (
            len(verdicts) != len(case.verdicts)
            or set(verdicts) != set(criteria)
            or any(not set(v.references) <= fields for v in case.verdicts)
        ):
            raise ValueError("Invalid judge verdicts")
        if len(case.checks) != 3 or {c.name for c in case.checks} != all_criteria:
            raise ValueError("Invalid judge check coverage")
        for check in case.checks:
            expected = (
                "not_applicable"
                if check.name not in criteria
                else "error"
                if case.error
                else "unmeasured"
                if judge.judging_method == "fixture"
                else verdicts[check.name].status
            )
            if (
                check.status != expected
                or check.dimension != "semantic"
                or check.value is not None
            ):
                raise ValueError("Judge check does not match verdict/applicability")
            fixed_reason = (
                "No policy-selected question to judge."
                if check.name not in criteria
                else "Required observations or a valid judge response were unavailable."
                if case.error
                else "Fixture verdict verifies mechanics only; semantic quality is unmeasured."
                if judge.judging_method == "fixture"
                else None
            )
            if fixed_reason is not None and check.reason != fixed_reason:
                raise ValueError("Invalid mechanical judge explanation")
            if (
                not case.error
                and judge.judging_method != "fixture"
                and check.name in criteria
                and check.reason != verdicts[check.name].reason
            ):
                raise ValueError("Judge explanation does not match its verdict")
    checks = [c for case in judge.cases for c in case.checks]
    expected_summaries = [
        JudgeSummary(**s.model_dump(), judging_method=judge.judging_method)
        for s in summarize(
            [
                ScoredCase(
                    case_id=c.case_id, group=c.group, target=c.target, checks=c.checks
                )
                for c in judge.cases
            ]
        )
    ]
    if (
        judge.summaries != expected_summaries
        or judge.failed_checks != sum(c.status == "fail" for c in checks)
        or judge.error_checks != sum(c.status == "error" for c in checks)
        or judge.unmeasured_checks != sum(c.status == "unmeasured" for c in checks)
        or judge.assessment_complete
        != (not any(c.status in ("error", "unmeasured") for c in checks))
        or judge.semantic_quality_measured
        != (
            judge.judging_method != "fixture"
            and any(c.status in ("pass", "fail") for c in checks)
        )
    ):
        raise ValueError("Judge summary does not match its checks")
    return judge


def load_report_inputs(
    root: Path, observations: bytes, metrics: bytes, judgments: bytes | None = None
) -> ReportInputs:
    execution = ExecutionReport.model_validate_json(observations, strict=True)
    if execution.version != "workspace-execution-v1":
        raise ValueError("Unsupported observation version")
    scores = ScoringReport.model_validate_json(metrics, strict=True)
    # Verify retained results against the current v1 metric contract, without
    # replacing them or rerunning scenarios. Stale scores need explicit rescoring.
    expected = score_observations(root, observations)
    metadata = {"generated_at", "code_revision", "dirty_worktree"}
    if canonical(scores.model_dump(mode="json", exclude=metadata)) != canonical(
        expected.model_dump(mode="json", exclude=metadata)
    ):
        raise ValueError("Metrics do not match observations/current scoring contract")
    judge = (
        validate_judge(root, execution, scores, judgments)
        if judgments is not None
        else None
    )
    return ReportInputs(
        execution,
        scores,
        judge,
        digest(metrics),
        digest(judgments) if judgments is not None else None,
    )
