"""Score approved observations and aggregate explicit per-check denominators."""

from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from api.evaluations.contracts import Case, CaseResult, CaseSet, Values, observations
from api.evaluations.metric_contracts import (
    Check,
    Checks,
    RetrievalMeasurement,
    ScoredCase,
    Summary,
)
from api.evaluations.metrics_approval import approval_checks
from api.evaluations.metrics_evidence import analysis_checks, retrieval_checks
from api.evaluations.metrics_intake import (
    clarification_checks,
    extraction_checks,
    failure_checks,
)


def check_plan(case: Case) -> list[tuple[str, str]]:
    """Keep the same check denominator when execution or dependent data is missing."""
    match case.target:
        case "extraction":
            plan = [
                ("output_schema", "structure"),
                ("service_allowed", "service_severity"),
                ("severity_allowed", "service_severity"),
                ("clarification_required", "clarification"),
                ("question_count", "clarification"),
            ]
            if "required_reasons" in case.expected:
                plan.append(("required_reasons", "clarification"))
            return plan
        case "clarification":
            plan = [
                (key, "structure" if key == "tool_dispatches" else "clarification")
                for key in (
                    "provider_calls",
                    "terminal_status",
                    "incomplete",
                    "tool_dispatches",
                    "answered_rounds",
                    "pause",
                    "final_pause",
                )
                if key in case.expected
            ]
            if "ordered_answers" in case.input:
                plan.append(("accepted_answers_in_order", "clarification"))
            return plan + [("clarification_schema", "structure")]
        case "approval":
            fields = (
                "execution_status",
                "saved_decision",
                "simulated_success",
                "tool_dispatches",
                "retry_dispatches",
                "current_version",
                "saved_result",
                "error_text_contains_raw_exception",
                "decision_request_status",
                "duplicate_result",
            )
            return [(key, "tool_policy") for key in fields if key in case.expected] + [
                ("exact_saved_binding", "tool_policy"),
                ("proposal_schema", "structure"),
            ]
        case "retrieval":
            plan = [
                ("exclusion_violations", "evidence"),
                ("duplicate_chunks", "evidence"),
                ("retrieval_schema", "structure"),
                ("citation_integrity", "evidence"),
            ]
            return plan + [
                (key, "evidence")
                for key in (
                    "returned_sections",
                    "foreign_text_in_result",
                    "superseded_text_in_result",
                    "hit_at_5",
                )
                if key in case.expected
            ]
        case "extraction_failure":
            return [(key, "structure") for key in case.expected]
        case "evidence_analysis":
            return [
                (
                    key,
                    "tool_policy"
                    if key in ("tool_dispatches", "approval_created")
                    else "evidence"
                    if key == "source_round_trips_as_data"
                    else "structure",
                )
                for key in case.expected
            ]


def score_case(case: Case, result: CaseResult, data: CaseSet, root: Path) -> ScoredCase:
    checks = Checks()
    profile = (
        data.applicability_profiles[case.applicability_profile]
        | case.applicability_overrides
    )
    retrieval = None
    available = result.execution_status != "error" and result.observed is not None
    if available:
        assert result.observed is not None
        match case.target:
            case "extraction":
                extraction_checks(case, result.observed, checks)
            case "clarification":
                clarification_checks(case, result.observed, checks)
            case "approval":
                approval_checks(case, result.observed, checks)
            case "extraction_failure":
                failure_checks(case, result.observed, checks)
            case "evidence_analysis":
                analysis_checks(case, result.observed, checks)
            case "retrieval":
                retrieval = retrieval_checks(case, result.observed, data, root, checks)
    elif case.target == "retrieval":
        retrieval = RetrievalMeasurement(
            relevance_applicable="acceptable_sections" in case.expected
        )
    observed_checks = {item.name: item for item in checks.items}
    planned: list[Check] = []
    for name, dimension in check_plan(case):
        planned.append(
            observed_checks.get(name)
            or Check(
                name=name,
                dimension=dimension,
                status="error",
                reason="Required observation is missing or execution did not complete.",
            )
        )
    present = {item.dimension for item in planned}
    for dimension, item in profile.items():
        if dimension in present:
            continue
        status = (
            "not_applicable"
            if item["assessment"] == "not_applicable"
            else "unmeasured"
            if available
            else "error"
        )
        planned.append(
            Check(
                name=dimension,
                dimension=dimension,
                status=status,
                reason=str(item["reason"])
                if status == "not_applicable"
                else "Semantic meaning requires reviewed judging."
                if available
                else "Execution did not produce observations for this dimension.",
            )
        )
    return ScoredCase(
        case_id=case.case_id,
        group=case.group,
        target=case.target,
        checks=planned,
        retrieval=retrieval,
    )


def summarize(cases: list[ScoredCase]) -> list[Summary]:
    return summarize_checks((c.mode, c.target, c.group, c.checks) for c in cases)


def summarize_checks(
    rows: Iterable[tuple[str, str, str, list[Check]]],
) -> list[Summary]:
    """Aggregate named checks without changing the caller's declared execution mode."""
    buckets: dict[tuple[str, str, str, str, str], list[Check]] = {}
    for mode, target, group, checks in rows:
        for check in checks:
            buckets.setdefault(
                (mode, target, group, check.dimension, check.name), []
            ).append(check)
    output: list[Summary] = []
    for (mode, target, group, dimension, metric), items in sorted(buckets.items()):
        counts = Counter(item.status for item in items)
        assessed = counts["pass"] + counts["fail"]
        output.append(
            Summary(
                mode=mode,
                target=target,
                group=group,
                dimension=dimension,
                metric=metric,
                passed=counts["pass"],
                failed=counts["fail"],
                errors=counts["error"],
                unmeasured=counts["unmeasured"],
                not_applicable=counts["not_applicable"],
                assessed_checks=assessed,
                total_checks=len(items),
                pass_rate_assessed_checks=counts["pass"] / assessed
                if assessed
                else None,
                incomplete=bool(counts["error"] or counts["unmeasured"]),
            )
        )
    return output


def retrieval_summary(cases: list[ScoredCase]) -> Values:
    results = [case.retrieval for case in cases if case.retrieval is not None]
    relevant = [item for item in results if item.relevance_applicable]
    successful = [item for item in relevant if item.successful]
    denominator = len(successful)
    return observations(
        dict(
            mode="fixture",
            relevance_successful_cases=denominator,
            relevance_failed_cases=len(relevant) - denominator,
            hit_rate_successful_cases=sum(bool(item.hit) for item in successful)
            / denominator
            if denominator
            else None,
            mean_reciprocal_rank_successful_cases=sum(
                item.reciprocal_rank or 0 for item in successful
            )
            / denominator
            if denominator
            else None,
            mean_listed_section_coverage_successful_cases=sum(
                item.listed_section_coverage or 0 for item in successful
            )
            / denominator
            if denominator
            else None,
            observed_exclusion_violations=sum(
                item.exclusion_violations or 0 for item in results
            ),
            observed_duplicate_chunks=sum(
                item.duplicate_chunks or 0 for item in results
            ),
            uninspected_cases=sum(
                item.exclusion_violations is None or item.duplicate_chunks is None
                for item in results
            ),
            failed_retrieval_cases=sum(not item.successful for item in results),
        )
    )
