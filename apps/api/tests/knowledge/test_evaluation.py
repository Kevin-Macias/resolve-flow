import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from api.knowledge.embeddings import EMBEDDING_PROFILE
from api.knowledge.evaluation import (
    CaseEvaluation,
    EvaluationReport,
    RetrievalCase,
    RetrievalCaseSet,
    evaluate_retrieval,
    load_cases,
    measure_result,
    validate_cases_for_corpus,
)
from api.knowledge.markdown import MarkdownDocument, load_manifest, prepare_markdown
from api.knowledge.retrieval import (
    DocumentRevision,
    RankedEvidence,
    RetrievalError,
    RetrievalFailure,
    RetrievalRequest,
    RetrievalResult,
    RetrievalScope,
)

ROOT = Path(__file__).resolve().parents[4]


def corpus() -> tuple[MarkdownDocument, ...]:
    return tuple(
        prepare_markdown(ROOT, meta)
        for meta in load_manifest(ROOT / "knowledge/manifest.json")
    )


def fixture_cases() -> RetrievalCaseSet:
    return RetrievalCaseSet.model_validate(
        {
            "version": "test-v1",
            "top_k": 5,
            "cases": [
                {
                    "case_id": "test",
                    "query": "Missing report",
                    "scope": {"allow_internal": True},
                    "acceptable": [
                        {
                            "document_id": "archived-report",
                            "version": "1",
                            "heading": "Interpretation",
                        },
                        {
                            "document_id": "archived-report",
                            "version": "1",
                            "heading": "Next steps and limits",
                        },
                    ],
                }
            ],
        }
    )


def evidence(headings: tuple[str, ...]) -> RetrievalResult:
    doc = next(doc for doc in corpus() if doc.metadata.document_id == "archived-report")
    items: list[RankedEvidence] = []
    for rank, heading in enumerate(headings, start=1):
        section = next(
            s
            for s in doc.sections
            if s.location.location.kind == "markdown"
            and s.location.location.heading_path[-1] == heading
        )
        items.append(
            RankedEvidence(
                chunk_id=UUID(int=rank),
                text=section.text,
                metadata=doc.metadata,
                passage=section.location,
                rank=rank,
                score=1 - rank / 10,
                score_metric="fixture",
            )
        )
    return RetrievalResult(evidence=tuple(items))


def request(case: RetrievalCase, top_k: int = 5) -> RetrievalRequest:
    return RetrievalRequest(
        query=case.query,
        scope=case.scope,
        active_revisions=tuple(
            DocumentRevision(
                document_id=doc.metadata.document_id, version=doc.metadata.version
            )
            for doc in corpus()
        ),
        service_code=case.service_code,
        top_k=top_k,
    )


@pytest.mark.parametrize(
    "headings,hit,rank,rr,coverage",
    [
        (("Interpretation",), True, 1, 1.0, 0.5),
        (("Checks", "Applicability", "Interpretation"), True, 3, 1 / 3, 0.5),
        (("Interpretation", "Next steps and limits"), True, 1, 1.0, 1.0),
        (("Checks",), False, None, 0, 0),
        ((), False, None, 0, 0),
    ],
)
def test_metric_arithmetic(
    headings: tuple[str, ...], hit: bool, rank: int | None, rr: float, coverage: float
) -> None:
    case = fixture_cases().cases[0]
    result = measure_result(case, request(case), evidence(headings), run_mode="fixture")
    assert result.hit == hit
    assert result.first_relevant_rank == rank
    assert result.reciprocal_rank == pytest.approx(rr)
    assert result.listed_section_coverage == coverage
    assert result.failure is None


def test_reviewed_cases_resolve_to_eligible_unique_sections() -> None:
    cases = load_cases(ROOT / "knowledge/evaluations/retrieval-v1.json")
    assert len(cases.cases) == 6 and cases.top_k == 5
    validate_cases_for_corpus(cases, corpus())
    assert cases.cases[-1].scope == RetrievalScope()
    altered = cases.cases[0].model_copy(update={"scope": RetrievalScope()})
    with pytest.raises(ValueError):
        validate_cases_for_corpus(
            cases.model_copy(update={"cases": (altered,)}), corpus()
        )
    missing = cases.cases[0].acceptable[0].model_copy(update={"heading": "Invented"})
    altered = cases.cases[0].model_copy(update={"acceptable": (missing,)})
    with pytest.raises(ValueError):
        validate_cases_for_corpus(
            cases.model_copy(update={"cases": (altered,)}), corpus()
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"acceptable": ()},
        {"query": " "},
        {"scope": {"allow_internal": "true"}},
        {
            "acceptable": [
                {"document_id": "archived-report", "version": "1", "heading": " "}
            ]
        },
    ],
)
def test_invalid_cases(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RetrievalCase.model_validate(fixture_cases().cases[0].model_dump() | changes)


def test_duplicate_cases_and_target_labels_rejected() -> None:
    cases = fixture_cases()
    with pytest.raises(ValidationError):
        RetrievalCaseSet.model_validate(
            cases.model_dump() | {"cases": cases.cases + cases.cases}
        )
    with pytest.raises(ValidationError):
        RetrievalCase.model_validate(
            cases.cases[0].model_dump() | {"acceptable": cases.cases[0].acceptable * 2}
        )


@pytest.mark.parametrize("case", ["exclusion", "duplicate", "both", "rank", "limit"])
def test_bad_response_is_counted_but_never_serialized(case: str) -> None:
    target = fixture_cases().cases[0]
    items = evidence(("Checks", "Interpretation")).evidence
    search = request(target)
    expected_exclusions = 0
    expected_duplicates = 0
    if case in {"exclusion", "both"}:
        search = search.model_copy(update={"scope": RetrievalScope()})
        expected_exclusions = 2
    if case in {"duplicate", "both"}:
        items = (items[0], items[0].model_copy(update={"rank": 2, "score": 0.7}))
        expected_duplicates = 1
    elif case == "rank":
        items = (items[0].model_copy(update={"rank": 2}),)
    elif case == "limit":
        search = search.model_copy(update={"top_k": 1})
    result = measure_result(
        target,
        search,
        RetrievalResult.model_construct(evidence=items),
        run_mode="fixture",
    )
    assert result.failure == RetrievalFailure.INVALID_RESPONSE
    assert result.hit is None and result.reciprocal_rank is None
    assert result.evidence == ()
    if case != "rank":
        assert result.exclusion_violations == expected_exclusions
        assert result.duplicate_chunks == expected_duplicates
    assert items[0].text not in result.model_dump_json()


class Responses:
    def __init__(self, responses: tuple[RetrievalResult | Exception, ...]) -> None:
        self.responses = iter(responses)

    async def search(self, request: RetrievalRequest) -> RetrievalResult:
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_aggregate_denominator_failures_and_report_roundtrip() -> None:
    base = fixture_cases()
    cases = base.model_copy(
        update={
            "cases": tuple(
                base.cases[0].model_copy(update={"case_id": str(index)})
                for index in range(3)
            )
        }
    )
    report = asyncio.run(
        evaluate_retrieval(
            Responses(
                (
                    evidence(("Checks", "Interpretation")),
                    RetrievalResult(),
                    RetrievalError(RetrievalFailure.TIMEOUT),
                )
            ),
            cases,
            corpus(),
            embedding_profile="offline-fixture",
        )
    )
    assert report.successful_cases == 2 and report.failed_cases == 1
    assert report.hit_rate_successful_cases == 0.5
    assert report.mean_reciprocal_rank_successful_cases == 0.25
    assert report.mean_listed_section_coverage_successful_cases == 0.25
    assert report.cases[1].failure is None and report.cases[1].hit is False
    assert (
        report.cases[2].failure == RetrievalFailure.TIMEOUT
        and report.cases[2].hit is None
    )
    assert report.run_mode == "fixture"
    assert len(report.corpus) == 8
    assert EvaluationReport.model_validate_json(report.model_dump_json()) == report


@pytest.mark.parametrize(
    "failure,expected",
    [
        (TimeoutError("secret"), RetrievalFailure.TIMEOUT),
        (RuntimeError("secret"), RetrievalFailure.UNAVAILABLE),
    ],
)
def test_all_failures_have_no_quality_metrics(
    failure: Exception, expected: RetrievalFailure
) -> None:
    report = asyncio.run(
        evaluate_retrieval(
            Responses((failure,)),
            fixture_cases(),
            corpus(),
            embedding_profile="offline-fixture",
        )
    )
    assert report.successful_cases == 0
    assert report.hit_rate_successful_cases is None
    assert report.mean_reciprocal_rank_successful_cases is None
    assert report.cases[0].failure == expected
    assert report.cases[0].exclusion_violations is None
    assert report.uninspected_cases == 1
    assert "secret" not in report.model_dump_json()


def test_fixture_scores_cannot_be_a_live_baseline() -> None:
    with pytest.raises(ValueError):
        asyncio.run(
            evaluate_retrieval(
                Responses((RetrievalResult(),)),
                fixture_cases(),
                corpus(),
                embedding_profile="test:1536:v1",
                run_mode="live",
            )
        )
    report = asyncio.run(
        evaluate_retrieval(
            Responses((evidence(("Interpretation",)),)),
            fixture_cases(),
            corpus(),
            embedding_profile=EMBEDDING_PROFILE,
            run_mode="live",
        )
    )
    assert (
        report.failed_cases == 1
        and report.cases[0].failure == RetrievalFailure.INVALID_RESPONSE
    )
    assert report.cases[0].evidence == ()


def test_failure_cannot_contain_quality_metrics() -> None:
    with pytest.raises(ValidationError):
        CaseEvaluation(
            case=fixture_cases().cases[0], failure=RetrievalFailure.TIMEOUT, hit=False
        )
    with pytest.raises(ValidationError):
        CaseEvaluation(case=fixture_cases().cases[0])


def test_live_script_requires_flag_before_provider_or_database_access() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "apps/api/scripts/evaluate_retrieval.py")],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "Explicit --live is required" in result.stderr
