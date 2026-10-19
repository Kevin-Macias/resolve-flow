"""Bounded semantic judging of approved extraction observations; no scenario execution."""

import asyncio
import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from api.evaluations.contracts import Case, CaseResult, observations
from api.evaluations.judge_contracts import (
    Criterion,
    JudgedCase,
    JudgeMethod,
    JudgeOutput,
    JudgeReport,
    JudgeSummary,
)
from api.evaluations.judge_prompt import (
    INSTRUCTIONS,
    PROMPT_ID,
    PROMPT_VERSION,
    RUBRIC_ID,
    RUBRIC_TEXT,
    RUBRIC_VERSION,
    digest,
)
from api.evaluations.metric_contracts import Check, ScoredCase
from api.evaluations.metrics import summarize
from api.evaluations.runner import code_provenance
from api.evaluations.scoring import validated_observations
from api.extraction.provider import LLMProvider, ModelSettings, ProviderResult
from api.extraction.schemas import ExtractionResult


class FixtureJudge:
    """Exercise the wire contract without making semantic quality judgments."""

    settings = ModelSettings(model="semantic-judge-fixture-v1")

    async def generate(
        self, instructions: str, input_text: str, output_schema: object = None
    ) -> ProviderResult:
        payload = json.loads(input_text)
        return ProviderResult(
            text=json.dumps(
                dict(
                    case_id=payload["case_id"],
                    verdicts=[
                        dict(
                            criterion=name,
                            status="unmeasured",
                            reason="Offline fixture judge does not assess semantic quality.",
                            references=["report"],
                        )
                        for name in payload["criteria"]
                    ],
                )
            )
        )


def judge_input(
    case: Case, result: CaseResult
) -> tuple[str, list[Criterion], set[str]]:
    if result.execution_status != "completed" or result.observed is None:
        raise ValueError("Missing observations")
    extraction = ExtractionResult.model_validate(result.observed["extraction"])
    clarification = result.observed["clarification"]
    if not isinstance(clarification, dict):
        raise ValueError("Missing clarification")
    questions = TypeAdapter(list[str]).validate_python(
        clarification["questions"], strict=True
    )
    criteria: list[Criterion] = ["factual_fidelity", "uncertainty_attribution"]
    if questions:
        criteria.append("question_relevance")
    fields = {"report", "semantic_notes", "selected_questions"} | {
        "extraction." + name for name in ExtractionResult.model_fields
    }
    payload = dict(
        case_id=case.case_id,
        report=case.input["report"],
        semantic_notes=case.semantic_review,
        extraction=extraction.model_dump(mode="json"),
        selected_questions=questions,
        criteria=criteria,
        reference_fields=sorted(fields),
    )
    return json.dumps(payload, sort_keys=True, ensure_ascii=False), criteria, fields


async def judge_case(
    case: Case,
    result: CaseResult,
    provider: LLMProvider,
    method: JudgeMethod,
    timeout_seconds: float,
) -> JudgedCase:
    criteria: list[Criterion] = [
        "factual_fidelity",
        "uncertainty_attribution",
        "question_relevance",
    ]
    error = None
    text = None
    output = None
    response = None
    attempts = 0
    fields: set[str] = set()
    try:
        text, criteria, fields = judge_input(case, result)
    except (ValueError, KeyError, TypeError):
        error = "missing_observations"
    if error is None:
        attempts = 1
        try:
            assert text is not None
            async with asyncio.timeout(timeout_seconds):
                response = await provider.generate(INSTRUCTIONS, text, JudgeOutput)
        except TimeoutError:
            error = "judge_timeout"
        except Exception:
            # Provider exceptions may contain credentials or raw request bodies.
            error = "judge_provider_failure"
        else:
            if response.refusal is not None:
                error = "judge_refusal"
            elif not response.text:
                error = "judge_empty_output"
            else:
                try:
                    output = JudgeOutput.model_validate_json(response.text, strict=True)
                    names = [v.criterion for v in output.verdicts]
                    if (
                        output.case_id != case.case_id
                        or len(names) != len(set(names))
                        or set(names) != set(criteria)
                        or any(not set(v.references) <= fields for v in output.verdicts)
                    ):
                        raise ValueError("Invalid verdict identities/references")
                except ValueError:
                    error = "judge_invalid_output"
                    output = None
    checks: list[Check] = []
    for criterion in (
        "factual_fidelity",
        "uncertainty_attribution",
        "question_relevance",
    ):
        if criterion not in criteria:
            status = "not_applicable"
            reason = "No policy-selected question to judge."
        elif error:
            status = "error"
            reason = "Required observations or a valid judge response were unavailable."
        else:
            assert output is not None
            verdict = next(v for v in output.verdicts if v.criterion == criterion)
            status = verdict.status if method != "fixture" else "unmeasured"
            reason = (
                verdict.reason
                if method != "fixture"
                else "Fixture verdict verifies mechanics only; semantic quality is unmeasured."
            )
        checks.append(
            Check(name=criterion, dimension="semantic", status=status, reason=reason)
        )
    return JudgedCase(
        case_id=case.case_id,
        group=case.group,
        judging_method=method,
        input_sha256=digest(text) if text is not None else None,
        checks=checks,
        verdicts=output.verdicts if output is not None else [],
        attempts=attempts,
        usage=observations(asdict(response.usage))
        if response is not None and response.usage is not None
        else None,
        resolved_model=response.resolved_model if response is not None else None,
        error=error,
    )


async def judge_observations(
    root: Path,
    raw: bytes,
    provider: LLMProvider,
    *,
    method: JudgeMethod = "fixture",
    timeout_seconds: float = 60,
) -> JudgeReport:
    if method not in ("fixture", "openai"):
        raise ValueError("Unsupported judging method")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("Judge timeout must be finite and positive")
    if not provider.settings.model.strip():
        raise ValueError("Explicit judge model is required")
    data, report = validated_observations(root, raw)
    by_id = {item.case_id: item for item in report.cases}
    cases = [
        await judge_case(case, by_id[case.case_id], provider, method, timeout_seconds)
        for case in data.cases
        if case.target == "extraction" and case.semantic_review
    ]
    # Detect changed case/spec/source inputs across an awaited judge call.
    validated_observations(root, raw)
    revision, dirty = code_provenance(root)
    checks = [check for case in cases for check in case.checks]
    summaries = summarize(
        [
            ScoredCase(
                case_id=c.case_id,
                group=c.group,
                target=c.target,
                mode=c.candidate_mode,
                checks=c.checks,
            )
            for c in cases
        ]
    )
    return JudgeReport(
        generated_at=datetime.now(UTC),
        judging_method=method,
        case_set_version=data.version,
        case_set_sha256=report.case_set_sha256,
        specification_sha256=report.specification_sha256,
        observation_sha256=digest(raw),
        rubric_id=RUBRIC_ID,
        rubric_version=RUBRIC_VERSION,
        rubric_sha256=digest(RUBRIC_TEXT),
        prompt_id=PROMPT_ID,
        prompt_version=PROMPT_VERSION,
        prompt_sha256=digest(INSTRUCTIONS),
        judge_provider="offline_fixture" if method == "fixture" else "openai",
        judge_settings=observations(asdict(provider.settings)),
        timeout_seconds=timeout_seconds,
        code_revision=revision,
        dirty_worktree=dirty,
        semantic_quality_measured=method != "fixture"
        and any(c.status in ("pass", "fail") for c in checks),
        assessment_complete=not any(
            c.status in ("error", "unmeasured") for c in checks
        ),
        failed_checks=sum(c.status == "fail" for c in checks),
        error_checks=sum(c.status == "error" for c in checks),
        unmeasured_checks=sum(c.status == "unmeasured" for c in checks),
        cases=cases,
        summaries=[
            JudgeSummary(**s.model_dump(), judging_method=method) for s in summaries
        ],
    )
