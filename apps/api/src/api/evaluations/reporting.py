"""Render validated evaluation artifacts as portable Markdown, entirely offline."""

import html
import json
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import cast

from api.evaluations.judge_prompt import digest
from api.evaluations.metric_contracts import Check, ScoredCase, Summary
from api.evaluations.report_comparison import (
    Transition,
    deterministic_changes,
    same_relevance_cohort,
    semantic_changes,
    semantic_comparison_limit,
)
from api.evaluations.report_inputs import ReportInputs, canonical

CONFIG_KEYS = (
    "provider",
    "prompt_id",
    "prompt_version",
    "embedding_profile",
    "chunk_strategy",
    "chunk_strategy_version",
    "checkpoint_backend",
    "clarification_backend",
    "live_calls",
    "latency_ms",
    "estimated_cost",
)
MODEL_KEYS = ("model", "temperature", "max_output_tokens", "reasoning_effort")


def cell(value: object) -> str:
    if value is None:
        return "not recorded"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.4g}"
    # Treat all variable text as literal table content, including model prose.
    text = " ".join(str(value).split())
    text = "".join(c for c in text if c.isprintable())
    return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", html.escape(text))


def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


def setting(value: object) -> object:
    # Configuration is an extensible JSON envelope. Render known scalar fields,
    # never dump arbitrary dictionaries that could contain credentials.
    return (
        value
        if isinstance(value, (str, int, float, bool)) or value is None
        else "unavailable"
    )


def settings(value: object) -> str:
    raw = cast(dict[str, object], value) if isinstance(value, dict) else {}
    return json.dumps({k: setting(raw.get(k)) for k in MODEL_KEYS}, sort_keys=True)


def totals(checks: Iterable[Check]) -> list[object]:
    counts = Counter(c.status for c in checks)
    return [
        counts[s] for s in ("pass", "fail", "error", "unmeasured", "not_applicable")
    ]


def metric_table(summaries: list[Summary]) -> str:
    return table(
        [
            "Target",
            "Group",
            "Dimension / metric",
            "Pass",
            "Fail",
            "Error",
            "Unmeasured",
            "N/A",
            "Assessed / total",
            "Pass / assessed",
            "Incomplete",
        ],
        (
            [
                s.target,
                s.group,
                s.dimension + " / " + s.metric,
                s.passed,
                s.failed,
                s.errors,
                s.unmeasured,
                s.not_applicable,
                f"{s.assessed_checks} / {s.total_checks}",
                f"{s.passed} / {s.assessed_checks} ({s.pass_rate_assessed_checks:.1%})"
                if s.assessed_checks
                else "null (0 assessed)",
                s.incomplete,
            ]
            for s in summaries
        ),
    )


def problem_table(cases: list[ScoredCase]) -> str:
    rows = [
        [c.case_id, c.group, c.target, v.dimension, v.name, v.status, v.reason]
        for c in cases
        for v in c.checks
        if v.status in ("fail", "error")
    ]
    return (
        table(
            ["Case", "Group", "Target", "Dimension", "Check", "Status", "Reason"], rows
        )
        if rows
        else "No deterministic failures or scoring errors."
    )


def classification_value(observed: dict[str, object], field: str) -> object:
    if field not in observed:
        return "unavailable"
    return "unknown (null)" if observed[field] is None else setting(observed[field])


def classification_table(bundle: ReportInputs) -> str:
    rows: list[list[object]] = []
    for case in bundle.execution.cases:
        if case.target != "extraction":
            continue
        extraction = (case.observed or {}).get("extraction")
        observed: dict[str, object] = (
            cast(dict[str, object], extraction) if isinstance(extraction, dict) else {}
        )

        rows.append(
            [
                case.case_id,
                canonical(case.expected.get("service_code_allowed")),
                classification_value(observed, "service_code"),
                canonical(case.expected.get("severity_allowed")),
                classification_value(observed, "severity"),
            ]
        )
    return table(
        [
            "Case",
            "Allowed service",
            "Observed service",
            "Allowed severity",
            "Observed severity",
        ],
        rows,
    )


def provenance(bundle: ReportInputs) -> str:
    e, s, j = bundle.execution, bundle.scores, bundle.judge
    rows: list[list[object]] = [
        ["Candidate mode", e.mode],
        ["Case set", s.case_set_version],
        ["Case SHA-256", s.case_set_sha256],
        ["Specification SHA-256", s.specification_sha256],
        ["Observation SHA-256", s.observation_sha256],
        ["Metrics SHA-256", bundle.scores_sha256],
        ["Metric contract", s.version],
        ["Executed at", e.generated_at.isoformat()],
        ["Execution revision", e.code_revision],
        ["Execution dirty", e.dirty_worktree],
        ["Scored at", s.generated_at.isoformat()],
        ["Scoring revision", s.code_revision],
        ["Scoring dirty", s.dirty_worktree],
        ["Configuration SHA-256", digest(canonical(e.configuration))],
    ]
    rows.extend(
        ["Candidate " + k, setting(e.configuration.get(k))] for k in CONFIG_KEYS
    )
    if j is not None:
        rows.extend(
            [
                ["Judgments SHA-256", bundle.judge_sha256],
                ["Judge contract", j.version],
                ["Judged at", j.generated_at.isoformat()],
                ["Judging method", j.judging_method],
                ["Judge provider", j.judge_provider],
                ["Judge settings", settings(j.judge_settings)],
                ["Rubric", j.rubric_id + " v" + j.rubric_version],
                ["Rubric SHA-256", j.rubric_sha256],
                ["Judge prompt", j.prompt_id + " v" + j.prompt_version],
                ["Judge prompt SHA-256", j.prompt_sha256],
                ["Judge timeout seconds", j.timeout_seconds],
                ["Judge max attempts", j.max_attempts],
                ["Judging revision", j.code_revision],
                ["Judging dirty", j.dirty_worktree],
            ]
        )
    corpus = table(
        ["Document", "Version", "Content SHA-256", "Metadata SHA-256"],
        (
            [
                s.get("document_id"),
                s.get("version"),
                s.get("content_hash"),
                s.get("metadata_hash"),
            ]
            for s in e.corpus
        ),
    )
    return table(["Provenance", "Value"], rows) + "\n\nCorpus snapshot:\n\n" + corpus


def extraction_calls(bundle: ReportInputs) -> str:
    rows: list[list[object]] = []
    for c in bundle.execution.cases:
        raw = c.observed.get("call") if c.observed is not None else None
        if not isinstance(raw, dict):
            continue
        usage = raw.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        rows.append(
            [
                c.case_id,
                settings(raw.get("model_settings")),
                setting(raw.get("prompt_id")),
                setting(raw.get("prompt_version")),
                setting(raw.get("attempts")),
                setting(usage.get("input_tokens")),
                setting(usage.get("output_tokens")),
                setting(usage.get("total_tokens")),
            ]
        )
    return table(
        [
            "Case",
            "Model settings",
            "Prompt",
            "Version",
            "Attempts",
            "Input tokens",
            "Output tokens",
            "Total tokens",
        ],
        rows,
    )


def semantic_section(bundle: ReportInputs) -> str:
    j = bundle.judge
    if j is None:
        return "No judgment artifact supplied. Semantic quality remains unmeasured."
    note = (
        "Fixture judge: semantic quality remains unmeasured; synthetic verdicts are not quality scores."
        if j.judging_method == "fixture"
        else "Model judgments are subjective assessments. Human calibration has not been established by this report."
    )
    cases = table(
        [
            "Case",
            "Resolved model",
            "Attempts",
            "Input tokens",
            "Output tokens",
            "Total tokens",
            "Error",
        ],
        (
            [
                c.case_id,
                c.resolved_model,
                c.attempts,
                setting((c.usage or {}).get("input_tokens")),
                setting((c.usage or {}).get("output_tokens")),
                setting((c.usage or {}).get("total_tokens")),
                c.error,
            ]
            for c in j.cases
        ),
    )
    details = table(
        ["Case", "Criterion", "Status", "Reason", "References"],
        (
            [
                c.case_id,
                v.name,
                v.status,
                v.reason,
                ", ".join(
                    next(
                        (x.references for x in c.verdicts if x.criterion == v.name),
                        list[str](),
                    )
                ),
            ]
            for c in j.cases
            for v in c.checks
        ),
    )
    return (
        f"Judging method: {cell(j.judging_method)}. Candidate mode: {cell(j.candidate_mode)}.\n\n{note}\n\n"
        + metric_table(list(j.summaries))
        + "\n\n"
        + cases
        + "\n\n"
        + details
    )


def transition_table(changes: list[Transition]) -> str:
    if not changes:
        return "No check status changes observed."
    return table(
        ["Case", "Metric", "Baseline", "Current", "Change"],
        ([c.case_id, c.metric, c.before, c.after, c.change] for c in changes),
    )


def comparison(current: ReportInputs, baseline: ReportInputs | None) -> str:
    if baseline is None:
        return "No baseline supplied. Regressions and improvement were not assessed."
    rows: list[list[object]] = []
    for label, bundle in (
        ("Baseline deterministic", baseline),
        ("Current deterministic", current),
    ):
        rows.append([label, *totals(v for c in bundle.scores.cases for v in c.checks)])
    for label, bundle in (
        ("Baseline semantic", baseline),
        ("Current semantic", current),
    ):
        if bundle.judge is not None:
            rows.append(
                [label, *totals(v for c in bundle.judge.cases for v in c.checks)]
            )
    note = (
        "Both runs use the same observation artifact. This is a comparison control, not a new candidate experiment."
        if baseline.scores.observation_sha256 == current.scores.observation_sha256
        else "Status changes describe these artifacts; they do not establish which design change caused them."
    )
    config_rows: list[list[object]] = [
        [
            "Execution revision",
            baseline.execution.code_revision,
            current.execution.code_revision,
        ],
        [
            "Execution dirty",
            baseline.execution.dirty_worktree,
            current.execution.dirty_worktree,
        ],
        [
            "Scoring revision",
            baseline.scores.code_revision,
            current.scores.code_revision,
        ],
        [
            "Scoring dirty",
            baseline.scores.dirty_worktree,
            current.scores.dirty_worktree,
        ],
        [
            "Configuration SHA-256",
            digest(canonical(baseline.execution.configuration)),
            digest(canonical(current.execution.configuration)),
        ],
    ]
    for key in CONFIG_KEYS:
        before, after = (
            baseline.execution.configuration.get(key),
            current.execution.configuration.get(key),
        )
        if canonical(before) != canonical(after):
            config_rows.append([key, setting(before), setting(after)])
    config_note = (
        table(["Changed candidate setting", "Baseline", "Current"], config_rows)
        if config_rows
        else "No changes in the displayed candidate configuration fields."
    )
    limit = semantic_comparison_limit(baseline, current)
    retrieval_rows: list[list[object]] = []
    quality_cohort = same_relevance_cohort(baseline, current)
    for name, after in current.scores.retrieval.items():
        if name == "mode":
            continue
        before = baseline.scores.retrieval.get(name)
        can_subtract = quality_cohort or not (
            name.startswith("mean_") or name == "hit_rate_successful_cases"
        )
        delta: object = "not comparable"
        if (
            can_subtract
            and isinstance(before, (int, float))
            and isinstance(after, (int, float))
        ):
            delta = after - before
        retrieval_rows.append([name, before, after, delta])
    return "\n\n".join(
        [
            note,
            table(["Scope", "Pass", "Fail", "Error", "Unmeasured", "N/A"], rows),
            config_note,
            "### Deterministic changes",
            transition_table(deterministic_changes(baseline, current)),
            "### Retrieval comparison",
            "Quality deltas require the same nonempty successful relevance cohort. Failure and uninspected counts remain separate.",
            table(["Measurement", "Baseline", "Current", "Delta"], retrieval_rows),
            "### Semantic changes",
            limit or transition_table(semantic_changes(baseline, current)),
            "### Baseline provenance",
            provenance(baseline),
            "Baseline extraction call settings and usage:\n\n"
            + extraction_calls(baseline),
            "Baseline semantic assessments:\n\n" + semantic_section(baseline),
        ]
    )


def render_report(current: ReportInputs, baseline: ReportInputs | None = None) -> str:
    statuses = Counter(c.execution_status for c in current.execution.cases)
    failures = [
        [c.case_id, c.target, c.error]
        for c in current.execution.cases
        if c.execution_status == "error"
    ]
    overview = [
        ["Deterministic", *totals(v for c in current.scores.cases for v in c.checks)]
    ]
    if current.judge is not None:
        overview.append(
            [
                "Semantic judge",
                *totals(v for c in current.judge.cases for v in c.checks),
            ]
        )
    return (
        "\n\n".join(
            [
                "# Workspace evaluation report",
                "Report format: workspace-report-v1. Generated at "
                + datetime.now(UTC).isoformat()
                + ".",
                "Candidate mode: fixture. These results describe simulation mechanics and fixture outputs; live candidate quality remains unmeasured.",
                f"Executed cases: {len(current.execution.cases)}; completed: {statuses['completed']}; executor errors: {statuses['error']}.",
                table(
                    ["Assessment scope", "Pass", "Fail", "Error", "Unmeasured", "N/A"],
                    overview,
                ),
                "Scopes have different check slots and are not added into a global quality score. A pass rate uses pass + fail only; errors/unmeasured make the assessment incomplete. Empty denominators are null.",
                "## Execution errors",
                table(["Case", "Target", "Error"], failures)
                if failures
                else "No executor errors.",
                "## Deterministic metrics",
                metric_table(current.scores.summaries),
                "Classification expectations and observations:\n\n"
                + classification_table(current),
                "## Deterministic failures and errors",
                problem_table(current.scores.cases),
                "Evidence and tool failures remain listed individually, independently of averages.",
                "## Retrieval measurements",
                table(
                    ["Measurement", "Value"],
                    ([k, v] for k, v in current.scores.retrieval.items()),
                ),
                "Hit, reciprocal rank, and listed-section coverage use successful relevance cases only. Failed/uninspected cases remain explicit. Only S03 has relevance labels; listed-section coverage is not exhaustive recall. No precision is inferred.",
                "## Semantic assessments",
                semantic_section(current),
                "## Baseline comparison",
                comparison(current, baseline),
                "## Current provenance",
                provenance(current),
                "Extraction call settings and usage:\n\n" + extraction_calls(current),
                "Dirty worktrees do not fully identify code through a revision alone. Missing model versions, usage, latency, and cost remain not recorded. Judgment explanations are untrusted model text; this report does not establish calibration or injection resistance.",
            ]
        )
        + "\n"
    )
