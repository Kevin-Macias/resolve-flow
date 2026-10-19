"""Closed subjective verdicts and provenance, separate from deterministic scores."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from api.evaluations.contracts import Values
from api.evaluations.metric_contracts import Check, Summary
from api.knowledge.metadata import KnowledgeContract

type Criterion = Literal[
    "factual_fidelity", "uncertainty_attribution", "question_relevance"
]
type JudgeMethod = Literal["fixture", "openai"]
type Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)
]


class Verdict(KnowledgeContract):
    criterion: Criterion
    status: Literal["pass", "fail", "unmeasured"]
    reason: Reason
    references: list[str] = Field(min_length=1, max_length=12)


class JudgeOutput(KnowledgeContract):
    case_id: str
    verdicts: list[Verdict] = Field(min_length=2, max_length=3)


class JudgedCase(KnowledgeContract):
    case_id: str
    group: str
    target: Literal["extraction"] = "extraction"
    candidate_mode: Literal["fixture"] = "fixture"
    judging_method: JudgeMethod
    input_sha256: str | None
    checks: list[Check]
    verdicts: list[Verdict]
    attempts: int
    usage: Values | None
    resolved_model: str | None
    error: (
        Literal[
            "missing_observations",
            "judge_timeout",
            "judge_provider_failure",
            "judge_refusal",
            "judge_empty_output",
            "judge_invalid_output",
        ]
        | None
    )


class JudgeSummary(Summary):
    judging_method: JudgeMethod


class JudgeReport(KnowledgeContract):
    version: Literal["workspace-judging-v1"] = "workspace-judging-v1"
    generated_at: datetime
    candidate_mode: Literal["fixture"] = "fixture"
    judging_method: JudgeMethod
    case_set_version: str
    case_set_sha256: str
    specification_sha256: str
    observation_sha256: str
    rubric_id: str
    rubric_version: str
    rubric_sha256: str
    prompt_id: str
    prompt_version: str
    prompt_sha256: str
    judge_provider: str
    judge_settings: Values
    timeout_seconds: float
    max_attempts: Literal[1] = 1
    code_revision: str | None
    dirty_worktree: bool | None
    semantic_quality_measured: bool
    assessment_complete: bool
    failed_checks: int
    error_checks: int
    unmeasured_checks: int
    cases: list[JudgedCase]
    summaries: list[JudgeSummary]
