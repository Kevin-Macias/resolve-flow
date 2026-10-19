"""Offline scoring of observations bound to the approved case set and source snapshot."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from api.evaluations.contracts import (
    FROZEN_SHA256,
    CaseSet,
    Values,
    load_case_set,
    observations,
)
from api.evaluations.evidence import load_sources
from api.evaluations.metric_contracts import ScoredCase, Summary
from api.evaluations.metrics import (
    retrieval_summary,
    score_case,
    summarize,
)
from api.evaluations.runner import ExecutionReport, code_provenance
from api.knowledge.metadata import KnowledgeContract


class ScoringReport(KnowledgeContract):
    version: Literal["workspace-metrics-v1"] = "workspace-metrics-v1"
    mode: Literal["fixture"] = "fixture"
    generated_at: datetime
    case_set_version: str
    case_set_sha256: str
    observation_sha256: str
    specification_sha256: str
    code_revision: str | None
    dirty_worktree: bool | None
    deterministic_checks_measured: Literal[True] = True
    semantic_quality_measured: Literal[False] = False
    assessment_complete: bool
    failed_checks: int
    error_checks: int
    unmeasured_checks: int
    cases: list[ScoredCase]
    summaries: list[Summary]
    retrieval: Values


def validated_observations(root: Path, raw: bytes) -> tuple[CaseSet, ExecutionReport]:
    """Bind observations to the reviewed cases and current permitted source snapshot."""
    data = load_case_set(root / "knowledge/evaluations/workspace-v1.json")
    report = ExecutionReport.model_validate_json(raw)
    if (
        report.case_set_version != data.version
        or report.case_set_sha256 != FROZEN_SHA256
    ):
        raise ValueError("Observation case provenance mismatch")
    if (
        report.specification_sha256
        != hashlib.sha256((root / data.specification).read_bytes()).hexdigest()
    ):
        raise ValueError("Observation specification mismatch")
    sources = load_sources(root, data, fixture_names=tuple(data.fixture_sources))
    corpus = [
        observations(
            dict(
                document_id=s.metadata.document_id,
                version=s.metadata.version,
                content_hash=s.content_hash,
                metadata_hash=s.metadata_hash,
            )
        )
        for s in sources
    ]
    if report.corpus != corpus:
        raise ValueError("Source snapshot differs from observations")
    by_id = {item.case_id: item for item in report.cases}
    if (
        len(by_id) != len(data.cases)
        or len(report.cases) != len(data.cases)
        or set(by_id) != {c.case_id for c in data.cases}
    ):
        raise ValueError("Observation identities are missing, repeated, or unknown")
    for case in data.cases:
        observed = by_id[case.case_id]
        if (
            observed.target != case.target
            or observed.group != case.group
            or json.dumps(observed.expected, sort_keys=True)
            != json.dumps(case.expected, sort_keys=True)
        ):
            raise ValueError(
                "Observation labels or identity differ from the approved case"
            )
    return data, report


def score_observations(root: Path, raw: bytes) -> ScoringReport:
    data, report = validated_observations(root, raw)
    by_id = {item.case_id: item for item in report.cases}
    cases = [score_case(case, by_id[case.case_id], data, root) for case in data.cases]
    failed = sum(c.status == "fail" for item in cases for c in item.checks)
    errors = sum(c.status == "error" for item in cases for c in item.checks)
    unmeasured = sum(c.status == "unmeasured" for item in cases for c in item.checks)
    revision, dirty = code_provenance(root)
    return ScoringReport(
        generated_at=datetime.now(UTC),
        case_set_version=data.version,
        case_set_sha256=FROZEN_SHA256,
        observation_sha256=hashlib.sha256(raw).hexdigest(),
        specification_sha256=report.specification_sha256,
        code_revision=revision,
        dirty_worktree=dirty,
        assessment_complete=not (errors or unmeasured),
        failed_checks=failed,
        error_checks=errors,
        unmeasured_checks=unmeasured,
        cases=cases,
        summaries=summarize(cases),
        retrieval=retrieval_summary(cases),
    )
