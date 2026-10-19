"""Typed metric records and strict expectation comparisons."""

import json
from typing import Literal

from pydantic import JsonValue

from api.evaluations.contracts import Values
from api.knowledge.metadata import KnowledgeContract

Status = Literal["pass", "fail", "error", "unmeasured", "not_applicable"]


class Check(KnowledgeContract):
    name: str
    dimension: str
    status: Status
    value: float | bool | None = None
    reason: str


class RetrievalMeasurement(KnowledgeContract):
    successful: bool = False
    hit: bool | None = None
    reciprocal_rank: float | None = None
    listed_section_coverage: float | None = None
    exclusion_violations: int | None = None
    duplicate_chunks: int | None = None
    relevance_applicable: bool


class ScoredCase(KnowledgeContract):
    case_id: str
    group: str
    target: str
    mode: Literal["fixture"] = "fixture"
    checks: list[Check]
    retrieval: RetrievalMeasurement | None = None


class Summary(KnowledgeContract):
    mode: str
    target: str
    group: str
    dimension: str
    metric: str
    passed: int
    failed: int
    errors: int
    unmeasured: int
    not_applicable: int
    assessed_checks: int
    total_checks: int
    pass_rate_assessed_checks: float | None
    incomplete: bool


class Checks:
    def __init__(self):
        self.items: list[Check] = []
        self.names: set[str] = set()

    def record(
        self,
        name: str,
        dimension: str,
        status: Status,
        value: float | bool | None = None,
        reason: str = "Compared with the approved case expectation.",
    ) -> None:
        if name in self.names:
            raise ValueError("Duplicate check")
        self.names.add(name)
        self.items.append(
            Check(
                name=name,
                dimension=dimension,
                status=status,
                value=value,
                reason=reason,
            )
        )

    def compare(
        self, name: str, dimension: str, actual: JsonValue, expected: JsonValue
    ) -> None:
        # bool is an int subclass in Python; true must not pass an expected count of 1.
        valid = json.dumps(actual, sort_keys=True) == json.dumps(
            expected, sort_keys=True
        )
        self.record(name, dimension, "pass" if valid else "fail", valid)

    def field(
        self, name: str, dimension: str, observed: Values, key: str, expected: JsonValue
    ) -> None:
        if key not in observed:
            self.record(
                name,
                dimension,
                "error",
                reason="Required observation was not recorded.",
            )
        else:
            self.compare(name, dimension, observed[key], expected)
