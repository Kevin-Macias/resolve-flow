"""Readable paired outputs and the predeclared adoption rule; no model judging."""

from api.evaluations.experiment_contracts import ExperimentReport, ExperimentReview
from api.evaluations.experiment_prompt import CASE_IDS
from api.evaluations.metric_contracts import Check
from api.evaluations.report_comparison import transitions
from api.evaluations.reporting import metric_table, table, totals, transition_table


def output_rows(report: ExperimentReport, cid: str) -> list[list[object]]:
    rows: list[list[object]] = []
    for c in report.cases:
        if c.case_id != cid:
            continue
        extraction = (c.observed or {}).get("extraction")
        if isinstance(extraction, dict):
            rows.extend([c.variant, key, value] for key, value in extraction.items())
    return rows


def adoption(report: ExperimentReport, review: ExperimentReview) -> str:
    if report.mode != "live":
        return "No adoption recommendation: fixture outputs cannot establish model improvement."
    if report.state != "completed" or any(
        c.status != "completed" for c in report.cases
    ):
        return "No adoption recommendation: the experiment is incomplete or contains failed extractions. Keep v3."
    models = {c.resolved_model for c in report.cases}
    if len(models) != 1 or any(not m or not m.strip() for m in models):
        return "No adoption recommendation: resolved model versions differ or are unavailable. Keep v3."
    baseline = {
        (c.case_id, v.name): v
        for c in report.cases
        if c.variant == "baseline"
        for v in c.checks
    }
    candidate = {
        (c.case_id, v.name): v
        for c in report.cases
        if c.variant == "candidate"
        for v in c.checks
    }
    if any(
        c.status in ("error", "unmeasured")
        for c in (*baseline.values(), *candidate.values())
    ):
        return "No clean adoption recommendation: deterministic assessments remain incomplete. Keep v3."
    if any(c.change == "regression" for c in transitions(baseline, candidate)):
        return "Do not adopt: a deterministic check regressed. Keep v3."
    if review.state != "reviewed":
        return (
            "Pending Kevin's semantic review. Keep v3 until the comparison is reviewed."
        )
    if any(a.status in ("unmeasured", "error") for a in review.assessments):
        return "No clean adoption recommendation: semantic assessments remain incomplete. Keep v3."
    before = {
        (a.case_id, a.criterion): Check(
            name=a.criterion, dimension="semantic", status=a.status, reason=a.reason
        )
        for a in review.assessments
        if a.variant == "baseline"
    }
    after = {
        (a.case_id, a.criterion): Check(
            name=a.criterion, dimension="semantic", status=a.status, reason=a.reason
        )
        for a in review.assessments
        if a.variant == "candidate"
    }
    changes = transitions(before, after)
    if any(c.change == "regression" for c in changes):
        return "Do not adopt: a reviewed semantic criterion regressed. Keep v3."
    if any(c.change == "improvement" for c in changes):
        return "The predeclared rule supports adopting the candidate on this small development-set comparison. Kevin owns the final adoption decision."
    return "No comparable semantic improvement was observed. Keep v3."


def render_experiment(report: ExperimentReport, review: ExperimentReview) -> str:
    before = {
        (c.case_id, v.name): v
        for c in report.cases
        if c.variant == "baseline"
        for v in c.checks
    }
    after = {
        (c.case_id, v.name): v
        for c in report.cases
        if c.variant == "candidate"
        for v in c.checks
    }
    parts = [
        "# RF-607 extraction prompt comparison",
        f"Candidate mode: {report.mode}. Experiment state: {report.state}.",
        "## Decision",
        adoption(report, review),
        "One output per prompt/case on six development cases is directional evidence. It does not establish statistical significance, broad reliability, or injection resistance. No judge-model calls were made.",
        "## Provenance",
        table(
            ["Field", "Value"],
            [
                ["Model", report.model_settings.model],
                ["Reasoning effort", report.model_settings.reasoning_effort],
                ["Output token cap", report.model_settings.max_output_tokens],
                ["Timeout per call", report.timeout_seconds],
                ["Max attempts", report.max_attempts],
                ["Experiment SHA-256", review.experiment_sha256],
                ["Case SHA-256", report.case_set_sha256],
                ["Specification SHA-256", report.specification_sha256],
                ["Rubric SHA-256", report.rubric_sha256],
                ["Baseline prompt version", report.baseline.version],
                ["Baseline prompt SHA-256", report.baseline.sha256],
                ["Candidate prompt version", report.candidate.version],
                ["Candidate prompt SHA-256", report.candidate.sha256],
                ["Code revision", report.code_revision],
                ["Dirty worktree", report.dirty_worktree],
                ["Generated at", report.generated_at.isoformat()],
                ["Review state", review.state],
                ["Reviewer", review.reviewer],
                ["Reviewed at", review.reviewed_at],
            ],
        ),
        "## Deterministic results",
        table(
            ["Variant", "Pass", "Fail", "Error", "Unmeasured", "N/A"],
            [
                [
                    v,
                    *totals(
                        k for c in report.cases if c.variant == v for k in c.checks
                    ),
                ]
                for v in ("baseline", "candidate")
            ],
        ),
        "### Baseline",
        metric_table(report.summaries["baseline"]),
        "### Candidate",
        metric_table(report.summaries["candidate"]),
        "### Status changes",
        transition_table(transitions(before, after)),
        "## Calls",
        table(
            [
                "Case",
                "Variant",
                "Status",
                "Attempts",
                "Resolved model",
                "Input tokens",
                "Output tokens",
                "Total tokens",
                "Error",
                "Started",
                "Finished",
            ],
            [
                [
                    c.case_id,
                    c.variant,
                    c.status,
                    c.attempts,
                    c.resolved_model,
                    (c.usage or {}).get("input_tokens"),
                    (c.usage or {}).get("output_tokens"),
                    (c.usage or {}).get("total_tokens"),
                    c.error,
                    c.started_at,
                    c.finished_at,
                ]
                for c in report.cases
            ],
        ),
        "## Outputs for Kevin's review",
    ]
    for cid in CASE_IDS:
        cases = [c for c in report.cases if c.case_id == cid]
        first = cases[0]
        parts.extend(
            [
                "### " + cid,
                table(
                    ["Original report", "Approved semantic notes"],
                    [[first.input_report, " ".join(first.semantic_notes)]],
                ),
                table(
                    ["Variant", "Field", "Observed value"],
                    output_rows(report, cid),
                ),
                table(
                    ["Variant", "Policy-selected clarification"],
                    [
                        [c.variant, (c.observed or {}).get("clarification")]
                        for c in cases
                    ],
                ),
            ]
        )
    parts.extend(
        [
            "## Semantic review",
            "Draft entries are pending human judgments, not measured scores. Only a sheet marked reviewed by Kevin can inform the adoption rule.",
            table(
                ["Case", "Variant", "Criterion", "Status", "Reason"],
                [
                    [a.case_id, a.variant, a.criterion, a.status, a.reason]
                    for a in review.assessments
                ],
            ),
        ]
    )
    return "\n\n".join(parts) + "\n"
