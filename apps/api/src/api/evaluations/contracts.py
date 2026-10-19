"""Closed case/report envelopes; expected labels never drive scenario execution."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, TypeAdapter

from api.knowledge.metadata import KnowledgeContract

FROZEN_VERSION = "workspace-evaluation-v1"
FROZEN_SHA256 = "8a74f4727db7e65a0ec117d16de01a050a6ac1fcda2b2f49a95ce73da87f91ca"
type Values = dict[str, JsonValue]
type Target = Literal[
    "extraction",
    "clarification",
    "retrieval",
    "evidence_analysis",
    "approval",
    "extraction_failure",
]


class Review(KnowledgeContract):
    status: Literal["approved"]
    reviewer: Literal["Kevin"]
    approved_on: Literal["2026-10-14"]


class Case(KnowledgeContract):
    case_id: str
    group: Literal["straightforward", "ambiguous", "adversarial", "failure_safety"]
    title: str
    target: Target
    allowed_modes: list[Literal["fixture", "live"]]
    trusted_context: str
    input: Values
    setup: Values
    expected: Values
    semantic_review: list[str]
    applicability_profile: str
    applicability_overrides: dict[str, Values] = Field(default_factory=dict)
    policy_references: list[str]
    review: Review


class CaseSet(KnowledgeContract):
    version: Literal["workspace-evaluation-v1"]
    specification: str
    review: Review
    default_mode: Literal["fixture"]
    default_corpus_manifest: str
    contexts: dict[str, Values]
    proposal_setup: Values
    fixture_sources: dict[str, Values]
    applicability_profiles: dict[str, dict[str, Values]]
    provider_response_fixtures: dict[str, Values]
    cases: list[Case]


def load_case_set(path: Path) -> CaseSet:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FROZEN_SHA256:
        raise ValueError("Case set differs from the approved frozen artifact")
    result = CaseSet.model_validate_json(raw)
    counts = Counter(case.group for case in result.cases)
    if counts != dict.fromkeys(
        ("straightforward", "ambiguous", "adversarial", "failure_safety"), 5
    ):
        raise ValueError("Invalid case group balance")
    if len({c.case_id for c in result.cases}) != 20:
        raise ValueError("Case identities must be unique")
    return result


class Assessment(KnowledgeContract):
    status: Literal["unmeasured", "not_applicable", "error"]
    reason: str


class CaseResult(KnowledgeContract):
    case_id: str
    group: str
    target: Target
    mode: Literal["fixture"] = "fixture"
    execution_status: Literal["completed", "error"]
    expected: Values
    observed: Values | None
    error: Literal["case_execution_failed", "case_timeout"] | None = None
    assessments: dict[str, Assessment]
    semantic_review: list[str]


def observations(value: object) -> Values:
    # Convert only an explicitly selected projection, never arbitrary graph state.
    adapter: TypeAdapter[Values] = TypeAdapter(Values)
    return adapter.validate_json(json.dumps(value))
