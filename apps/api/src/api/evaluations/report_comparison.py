"""Explain baseline status transitions without mixing measurements or methods."""

from dataclasses import dataclass

from api.evaluations.metric_contracts import Check
from api.evaluations.report_inputs import ReportInputs, canonical


@dataclass(frozen=True)
class Transition:
    case_id: str
    metric: str
    before: str
    after: str
    change: str


def transitions(
    before: dict[tuple[str, str], Check], after: dict[tuple[str, str], Check]
) -> list[Transition]:
    if before.keys() != after.keys():
        raise ValueError("Different metric cohorts cannot be compared")
    changes: list[Transition] = []
    for (case_id, name), old in sorted(before.items()):
        new = after[case_id, name]
        if old.status == new.status:
            continue
        label = (
            "regression"
            if (old.status, new.status) == ("pass", "fail")
            else "improvement"
            if (old.status, new.status) == ("fail", "pass")
            else "applicability changed"
            if "not_applicable" in (old.status, new.status)
            else "assessment lost"
            if old.status in ("pass", "fail")
            else "assessment gained"
            if new.status in ("pass", "fail")
            else "assessment status changed"
        )
        changes.append(Transition(case_id, name, old.status, new.status, label))
    return changes


def deterministic_changes(
    baseline: ReportInputs, current: ReportInputs
) -> list[Transition]:
    return transitions(
        {(c.case_id, v.name): v for c in baseline.scores.cases for v in c.checks},
        {(c.case_id, v.name): v for c in current.scores.cases for v in c.checks},
    )


def semantic_comparison_limit(
    baseline: ReportInputs, current: ReportInputs
) -> str | None:
    old, new = baseline.judge, current.judge
    if old is None or new is None:
        return "Semantic comparison unavailable: judgments are missing from one or both runs."
    keys = (
        "candidate_mode",
        "judging_method",
        "rubric_id",
        "rubric_version",
        "rubric_sha256",
        "prompt_id",
        "prompt_version",
        "prompt_sha256",
        "judge_provider",
        "judge_settings",
        "timeout_seconds",
        "max_attempts",
    )
    if any(canonical(getattr(old, k)) != canonical(getattr(new, k)) for k in keys):
        return "Semantic comparison unavailable: judge method, rubric, prompt, or settings changed."
    if old.judging_method == "fixture":
        return "Fixture judgments do not support semantic quality comparisons."
    old_models = {c.case_id: c.resolved_model for c in old.cases}
    new_models = {c.case_id: c.resolved_model for c in new.cases}
    if any(
        not v or not v.strip() for v in (*old_models.values(), *new_models.values())
    ):
        return "Semantic comparison unavailable: a resolved judge model version is unknown."
    if old_models != new_models:
        return "Semantic comparison unavailable: resolved judge model versions changed."
    return None


def semantic_changes(baseline: ReportInputs, current: ReportInputs) -> list[Transition]:
    if semantic_comparison_limit(baseline, current) is not None:
        return []
    assert baseline.judge is not None and current.judge is not None
    return transitions(
        {(c.case_id, v.name): v for c in baseline.judge.cases for v in c.checks},
        {(c.case_id, v.name): v for c in current.judge.cases for v in c.checks},
    )


def same_relevance_cohort(baseline: ReportInputs, current: ReportInputs) -> bool:
    def cohort(bundle: ReportInputs) -> set[str]:
        return {
            c.case_id
            for c in bundle.scores.cases
            if c.retrieval is not None
            and c.retrieval.relevance_applicable
            and c.retrieval.successful
        }

    return bool(cohort(baseline)) and cohort(baseline) == cohort(current)
