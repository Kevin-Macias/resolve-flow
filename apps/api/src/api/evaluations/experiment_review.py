"""Validate saved experiment evidence and prepare Kevin's unfilled review sheet."""

from dataclasses import asdict
from pathlib import Path

from pydantic import TypeAdapter

from api.evaluations.contracts import load_case_set
from api.evaluations.experiment import refresh
from api.evaluations.experiment_contracts import (
    ExperimentReport,
    ExperimentReview,
    HumanAssessment,
)
from api.evaluations.experiment_prompt import CASE_IDS, VARIANTS, prompts, snapshot
from api.evaluations.judge_contracts import Criterion
from api.evaluations.judge_prompt import RUBRIC_TEXT, digest
from api.evaluations.report_inputs import canonical
from api.extraction.clarification import decide_clarification
from api.extraction.schemas import ExtractionResult


def load_experiment(root: Path, raw: bytes) -> ExperimentReport:
    report = ExperimentReport.model_validate_json(raw, strict=True)
    data = load_case_set(root / "knowledge/evaluations/workspace-v1.json")
    if (
        report.case_set_version != data.version
        or report.case_set_sha256
        != digest((root / "knowledge/evaluations/workspace-v1.json").read_bytes())
        or report.specification_sha256
        != digest((root / data.specification).read_bytes())
        or report.rubric_sha256 != digest(RUBRIC_TEXT)
        or not report.model_settings.model.strip()
        or report.model_settings.max_output_tokens != 2048
    ):
        raise ValueError("Experiment input provenance differs")
    pair = prompts()
    if report.baseline != snapshot(pair["baseline"]) or report.candidate != snapshot(
        pair["candidate"]
    ):
        raise ValueError("Experiment prompt differs from the approved pair")
    definitions = {c.case_id: c for c in data.cases if c.case_id in CASE_IDS}
    keys = {(cid, v) for cid in CASE_IDS for v in VARIANTS}
    if (
        len(report.cases) != 12
        or {(c.case_id, c.variant) for c in report.cases} != keys
    ):
        raise ValueError("Experiment cohort is missing or repeated")
    for c in report.cases:
        definition = definitions[c.case_id]
        if (
            c.group != definition.group
            or c.input_report != definition.input["report"]
            or canonical(c.expected) != canonical(definition.expected)
            or c.semantic_notes != definition.semantic_review
        ):
            raise ValueError("Experiment labels or report differ")
        if c.status in ("completed", "error"):
            if c.started_at is None or c.finished_at is None or c.attempts != 1:
                raise ValueError("Invalid terminal call record")
        if c.status == "completed":
            if c.error is not None or c.observed is None:
                raise ValueError("Missing completed extraction")
            extraction = ExtractionResult.model_validate(c.observed["extraction"])
            clarification = decide_clarification(extraction)
            expected_clarification = dict(
                reasons=list(clarification.reasons),
                questions=list(clarification.questions),
                needs_clarification=clarification.needs_clarification,
            )
            if canonical(c.observed["clarification"]) != canonical(
                expected_clarification
            ):
                raise ValueError("Saved clarification does not match actual policy")
            call = c.observed["call"]
            if (
                not isinstance(call, dict)
                or call.get("prompt_id") != pair[c.variant].id
                or call.get("prompt_version") != pair[c.variant].version
                or call.get("attempts") != 1
                or canonical(call.get("model_settings"))
                != canonical(asdict(report.model_settings))
                or canonical(call.get("usage")) != canonical(c.usage)
            ):
                raise ValueError("Call settings or usage differ")
        elif c.observed is not None or (c.status == "error" and c.error is None):
            raise ValueError("Invalid unavailable extraction")
        if report.state == "completed" and c.status not in ("completed", "error"):
            raise ValueError("Completed experiment has unattempted slots")
    calculated = refresh(report, definitions)
    if report.cases != calculated.cases or report.summaries != calculated.summaries:
        raise ValueError("Experiment scores are inconsistent")
    return report


CRITERION = TypeAdapter[Criterion](Criterion)


def review_template(report: ExperimentReport, raw: bytes) -> ExperimentReview:
    return ExperimentReview(
        experiment_sha256=digest(raw),
        assessments=[
            HumanAssessment(
                case_id=c.case_id,
                variant=c.variant,
                criterion=CRITERION.validate_python(check.name),
                status=check.status,
                reason=check.reason,
            )
            for c in report.cases
            for check in c.semantic_checks
        ],
    )


def load_review(
    report: ExperimentReport, raw: bytes, review_raw: bytes
) -> ExperimentReview:
    review = ExperimentReview.model_validate_json(review_raw, strict=True)
    expected = review_template(report, raw)

    def key(a: HumanAssessment) -> tuple[str, str, str]:
        return a.case_id, a.variant, a.criterion

    rows = {key(a): a for a in review.assessments}
    if (
        review.experiment_sha256 != digest(raw)
        or len(rows) != len(review.assessments)
        or rows.keys() != {key(a) for a in expected.assessments}
    ):
        raise ValueError("Review identities or experiment hash differ")
    if review.state == "reviewed" and (
        review.reviewer != "Kevin" or review.reviewed_at is None
    ):
        raise ValueError("Reviewed sheet needs Kevin and a review timestamp")
    if review.state == "draft" and (
        review.reviewer is not None or review.reviewed_at is not None
    ):
        raise ValueError("Draft sheet cannot claim a reviewer")
    for original in expected.assessments:
        row = rows[key(original)]
        if original.status in ("error", "not_applicable"):
            if row.status != original.status:
                raise ValueError(
                    "Review cannot override unavailable/not-applicable checks"
                )
        elif row.status not in ("pass", "fail", "unmeasured"):
            raise ValueError("Invalid human semantic judgment")
    return review
