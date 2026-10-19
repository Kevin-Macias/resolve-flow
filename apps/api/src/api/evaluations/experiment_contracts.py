"""Separate six-case prompt experiment; never a mixed fixture/live workspace run."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from api.evaluations.contracts import Values
from api.evaluations.judge_contracts import Criterion, Reason
from api.evaluations.metric_contracts import Check, Status, Summary
from api.extraction.provider import ModelSettings
from api.knowledge.metadata import KnowledgeContract

type Variant = Literal["baseline", "candidate"]


class PromptSnapshot(KnowledgeContract):
    id: str
    version: str
    instructions: str
    sha256: str


class ExperimentCase(KnowledgeContract):
    case_id: str
    group: str
    variant: Variant
    input_report: str
    expected: Values
    semantic_notes: list[str]
    status: Literal["pending", "running", "completed", "error"] = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempts: int = Field(default=0, strict=True, ge=0, le=1)
    resolved_model: str | None = None
    usage: Values | None = None
    observed: Values | None = None
    error: (
        Literal[
            "refusal",
            "empty_output",
            "malformed_json",
            "invalid_data",
            "provider_error",
            "unexpected_provider_failure",
            "cancelled",
        ]
        | None
    ) = None
    provider_failure: Literal["timeout", "transient", "permanent"] | None = None
    checks: list[Check] = Field(default_factory=list[Check])
    semantic_checks: list[Check] = Field(default_factory=list[Check])


class ExperimentReport(KnowledgeContract):
    version: Literal["workspace-extraction-experiment-v1"] = (
        "workspace-extraction-experiment-v1"
    )
    mode: Literal["fixture", "live"]
    state: Literal["running", "completed", "cancelled"]
    generated_at: datetime
    case_set_version: str
    case_set_sha256: str
    specification_sha256: str
    rubric_sha256: str
    baseline: PromptSnapshot
    candidate: PromptSnapshot
    model_settings: ModelSettings
    max_attempts: Literal[1] = 1
    timeout_seconds: Literal[60] = 60
    code_revision: str | None
    dirty_worktree: bool | None
    cases: list[ExperimentCase]
    summaries: dict[Variant, list[Summary]]


class HumanAssessment(KnowledgeContract):
    case_id: str
    variant: Variant
    criterion: Criterion
    status: Status
    reason: Reason


class ExperimentReview(KnowledgeContract):
    version: Literal["workspace-extraction-review-v1"] = (
        "workspace-extraction-review-v1"
    )
    experiment_sha256: str
    state: Literal["draft", "reviewed"] = "draft"
    reviewer: Literal["Kevin"] | None = None
    reviewed_at: datetime | None = None
    assessments: list[HumanAssessment]
