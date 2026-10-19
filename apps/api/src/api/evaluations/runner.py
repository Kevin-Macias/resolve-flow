"""Run all approved fixture scenarios and retain observations without quality scores."""

import asyncio
import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from api.evaluations.approval import execute_approval
from api.evaluations.contracts import (
    Assessment,
    Case,
    CaseResult,
    CaseSet,
    Values,
    load_case_set,
    observations,
)
from api.evaluations.database import EvaluationDatabase, evaluation_database
from api.evaluations.evidence import execute_analysis, execute_retrieval, load_sources
from api.evaluations.extraction import execute_clarification, execute_extraction
from api.extraction.prompts import EXTRACTION_PROMPT
from api.knowledge.chunks import CHUNK_STRATEGY, CHUNK_STRATEGY_VERSION
from api.knowledge.metadata import KnowledgeContract


class ExecutionReport(KnowledgeContract):
    version: str = "workspace-execution-v1"
    case_set_version: str
    case_set_sha256: str
    specification_sha256: str
    mode: Literal["fixture"] = "fixture"
    generated_at: datetime
    code_revision: str | None
    dirty_worktree: bool | None
    corpus: list[Values]
    configuration: Values
    completed_cases: int
    error_cases: int
    cases: list[CaseResult]
    quality_measured: Literal[False] = False


def code_provenance(root: Path) -> tuple[str | None, bool | None]:
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=root,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).strip()
        )
        return revision, dirty
    except (OSError, subprocess.SubprocessError):
        return None, None


def assessments(case: Case, data: CaseSet) -> dict[str, Assessment]:
    profile = (
        data.applicability_profiles[case.applicability_profile]
        | case.applicability_overrides
    )
    return {
        name: Assessment(
            status="not_applicable"
            if item["assessment"] == "not_applicable"
            else "unmeasured",
            reason=str(item["reason"])
            if item["assessment"] == "not_applicable"
            else "Semantic assessment requires reviewed judging."
            if item["assessment"] == "semantic_review"
            else "Observation recorded; deterministic scoring belongs to RF-604.",
        )
        for name, item in profile.items()
    }


async def execute_case(
    case: Case,
    data: CaseSet,
    root: Path,
    database: EvaluationDatabase | None,
    *,
    timeout_seconds: float = 60,
) -> CaseResult:
    observed = None
    error = None
    try:
        if "fixture" not in case.allowed_modes:
            raise ValueError("Case does not allow fixture execution")
        async with asyncio.timeout(timeout_seconds):
            match case.target:
                case "extraction" | "extraction_failure":
                    observed = await execute_extraction(case, data)
                case "clarification":
                    observed = await execute_clarification(case, data)
                case "retrieval":
                    observed = await execute_retrieval(case, data, root)
                case "evidence_analysis":
                    observed = await execute_analysis(case, data, root)
                case "approval":
                    if database is None:
                        raise ValueError("Approval requires evaluation database")
                    observed = await execute_approval(case, database)
    except TimeoutError:
        error = "case_timeout"
    except Exception:
        # Raw exceptions may contain database URLs, provider text, or passages.
        error = "case_execution_failed"
    assessment = assessments(case, data)
    if error:
        assessment = {
            name: item
            if item.status == "not_applicable"
            else Assessment(
                status="error", reason="Case execution could not produce observations."
            )
            for name, item in assessment.items()
        }
    return CaseResult(
        case_id=case.case_id,
        group=case.group,
        target=case.target,
        execution_status="error" if error else "completed",
        expected=case.expected,
        observed=observed,
        error=error,
        assessments=assessment,
        semantic_review=case.semantic_review,
    )


async def run_evaluation(root: Path, database_url: str) -> ExecutionReport:
    path = root / "knowledge/evaluations/workspace-v1.json"
    data = load_case_set(path)
    # Preflight every reference before making database changes.
    sources = load_sources(root, data, fixture_names=tuple(data.fixture_sources))
    for case in data.cases:
        if (
            case.trusted_context not in data.contexts
            or case.applicability_profile not in data.applicability_profiles
        ):
            raise ValueError("Invalid case references")
        for policy in case.policy_references:
            if not (root / policy).is_file():
                raise ValueError("Missing policy")
    results: list[CaseResult] = []
    async with evaluation_database(database_url) as database:
        for case in data.cases:
            results.append(await execute_case(case, data, root, database))
    current_sources = load_sources(
        root, data, fixture_names=tuple(data.fixture_sources)
    )
    if sources != current_sources or load_case_set(path) != data:
        raise ValueError("Evaluation inputs changed during execution")
    revision, dirty = code_provenance(root)
    return ExecutionReport(
        case_set_version=data.version,
        case_set_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        specification_sha256=hashlib.sha256(
            (root / data.specification).read_bytes()
        ).hexdigest(),
        generated_at=datetime.now(UTC),
        code_revision=revision,
        dirty_worktree=dirty,
        corpus=[
            observations(
                dict(
                    document_id=s.metadata.document_id,
                    version=s.metadata.version,
                    content_hash=s.content_hash,
                    metadata_hash=s.metadata_hash,
                )
            )
            for s in sources
        ],
        configuration=observations(
            dict(
                provider="evaluation-fixture-v1",
                prompt_id=EXTRACTION_PROMPT.id,
                prompt_version=EXTRACTION_PROMPT.version,
                embedding_profile=None,
                chunk_strategy=CHUNK_STRATEGY,
                chunk_strategy_version=CHUNK_STRATEGY_VERSION,
                checkpoint_backend="temporary_postgresql_schema_for_approval",
                clarification_backend="memory",
                live_calls=False,
                latency_ms=None,
                estimated_cost=None,
            )
        ),
        completed_cases=sum(r.execution_status == "completed" for r in results),
        error_cases=sum(r.execution_status == "error" for r in results),
        cases=results,
    )
