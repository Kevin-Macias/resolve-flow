"""Run the approved prompt pair once per case with durable progress callbacks."""

import asyncio
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from api.evaluations.contracts import Case, load_case_set, observations
from api.evaluations.experiment_contracts import (
    ExperimentCase,
    ExperimentReport,
)
from api.evaluations.experiment_prompt import CASE_IDS, VARIANTS, prompts, snapshot
from api.evaluations.judge_prompt import RUBRIC_TEXT, digest
from api.evaluations.metric_contracts import Check, Checks
from api.evaluations.metrics import check_plan, summarize_checks
from api.evaluations.metrics_intake import extraction_checks
from api.evaluations.runner import code_provenance
from api.extraction.provider import LLMProvider, ProviderResult
from api.extraction.service import ExtractionError, RetryPolicy, extract_issue_report


class RecordedProvider:
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.settings = provider.settings
        self.result: ProviderResult | None = None
        self.calls = 0

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        self.calls += 1
        if self.calls > 1:
            raise ValueError("Experiment retry is forbidden")
        self.result = await self.provider.generate(
            instructions, input_text, output_schema
        )
        return self.result


def checks_for(case: Case, result: ExperimentCase) -> tuple[list[Check], list[Check]]:
    measured = Checks()
    if result.status == "completed" and result.observed is not None:
        extraction_checks(case, result.observed, measured)
    found = {c.name: c for c in measured.items}
    checks = [
        found.get(name)
        or Check(
            name=name,
            dimension=dimension,
            status="error" if result.status == "error" else "unmeasured",
            reason="Extraction did not produce a valid assessable observation.",
        )
        for name, dimension in check_plan(case)
    ]
    if result.error in ("malformed_json", "invalid_data"):
        checks = [
            c.model_copy(
                update=dict(
                    status="fail",
                    value=False,
                    reason="Extraction output failed validation.",
                )
            )
            if c.name == "output_schema"
            else c
            for c in checks
        ]
    clarification = (result.observed or {}).get("clarification")
    no_questions = (
        isinstance(clarification, dict) and clarification.get("questions") == []
    )
    semantic = [
        Check(
            name=name,
            dimension="semantic",
            status="error"
            if result.status == "error"
            else "not_applicable"
            if name == "question_relevance" and no_questions
            else "unmeasured",
            reason="No policy-selected questions."
            if name == "question_relevance" and no_questions
            else "Kevin's semantic review is required.",
        )
        for name in (
            "factual_fidelity",
            "uncertainty_attribution",
            "question_relevance",
        )
    ]
    return checks, semantic


def refresh(report: ExperimentReport, definitions: dict[str, Case]) -> ExperimentReport:
    cases: list[ExperimentCase] = []
    for result in report.cases:
        checks, semantic = checks_for(definitions[result.case_id], result)
        cases.append(
            result.model_copy(update=dict(checks=checks, semantic_checks=semantic))
        )
    return report.model_copy(
        update=dict(
            cases=cases,
            summaries={
                variant: summarize_checks(
                    (report.mode, "extraction", c.group, c.checks)
                    for c in cases
                    if c.variant == variant
                )
                for variant in VARIANTS
            },
        )
    )


async def run_experiment(
    root: Path,
    provider: LLMProvider,
    *,
    mode: Literal["fixture", "live"] = "fixture",
    progress: Callable[[ExperimentReport], None] | None = None,
) -> ExperimentReport:
    if (
        mode not in ("fixture", "live")
        or not provider.settings.model.strip()
        or provider.settings.max_output_tokens != 2048
    ):
        raise ValueError("Invalid experiment mode/model/token cap")
    pair = prompts()
    case_path = root / "knowledge/evaluations/workspace-v1.json"
    data = load_case_set(case_path)
    definitions = {c.case_id: c for c in data.cases if c.case_id in CASE_IDS}
    spec_hash = digest((root / data.specification).read_bytes())
    revision, dirty = code_provenance(root)
    report = ExperimentReport(
        mode=mode,
        state="running",
        generated_at=datetime.now(UTC),
        case_set_version=data.version,
        case_set_sha256=digest(case_path.read_bytes()),
        specification_sha256=spec_hash,
        rubric_sha256=digest(RUBRIC_TEXT),
        baseline=snapshot(pair["baseline"]),
        candidate=snapshot(pair["candidate"]),
        model_settings=provider.settings,
        code_revision=revision,
        dirty_worktree=dirty,
        cases=[
            ExperimentCase(
                case_id=cid,
                group=definitions[cid].group,
                variant=variant,
                input_report=str(definitions[cid].input["report"]),
                expected=definitions[cid].expected,
                semantic_notes=definitions[cid].semantic_review,
            )
            for cid in CASE_IDS
            for variant in VARIANTS
        ],
        summaries={},
    )

    def publish() -> None:
        nonlocal report
        report = refresh(report, definitions)
        if progress is not None:
            progress(report)

    publish()
    for index in range(len(report.cases)):
        if provider.settings != report.model_settings:
            raise ValueError("Provider settings changed during experiment")
        case = report.cases[index]
        record = case.model_copy(
            update=dict(status="running", started_at=datetime.now(UTC))
        )
        report.cases[index] = record
        publish()
        recorder = RecordedProvider(provider)
        try:
            outcome = await extract_issue_report(
                case.input_report,
                recorder,
                RetryPolicy(max_attempts=1, timeout_seconds=60),
                prompt=pair[case.variant],
            )
        except ExtractionError as error:
            record = record.model_copy(
                update=dict(
                    status="error",
                    error=error.reason.value,
                    provider_failure=error.provider_failure_kind.value
                    if error.provider_failure_kind
                    else None,
                )
            )
        except asyncio.CancelledError:
            report.cases[index] = record.model_copy(
                update=dict(
                    status="error",
                    error="cancelled",
                    attempts=recorder.calls,
                    finished_at=datetime.now(UTC),
                )
            )
            report = report.model_copy(update=dict(state="cancelled"))
            publish()
            raise
        except Exception:
            record = record.model_copy(
                update=dict(status="error", error="unexpected_provider_failure")
            )
        else:
            record = record.model_copy(
                update=dict(
                    status="completed",
                    observed=observations(
                        dict(
                            extraction=outcome.result.model_dump(mode="json"),
                            clarification=dict(
                                reasons=list(outcome.clarification.reasons),
                                questions=list(outcome.clarification.questions),
                                needs_clarification=outcome.clarification.needs_clarification,
                            ),
                            call=asdict(outcome.call),
                        )
                    ),
                )
            )
        response = recorder.result
        report.cases[index] = record.model_copy(
            update=dict(
                finished_at=datetime.now(UTC),
                attempts=recorder.calls,
                resolved_model=response.resolved_model if response else None,
                usage=observations(asdict(response.usage))
                if response and response.usage
                else None,
            )
        )
        publish()
    if (
        provider.settings != report.model_settings
        or load_case_set(case_path) != data
        or digest((root / data.specification).read_bytes()) != spec_hash
    ):
        raise ValueError(
            "Experiment inputs changed during execution; retained progress is incomplete"
        )
    report = report.model_copy(update=dict(state="completed"))
    publish()
    return report
