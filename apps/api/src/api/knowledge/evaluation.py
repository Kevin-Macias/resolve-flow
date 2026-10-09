"""Reviewed retrieval cases and measurements; fixture results are not live quality."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, model_validator

from api.knowledge.chunks import CHUNK_STRATEGY, CHUNK_STRATEGY_VERSION
from api.knowledge.citations import verify_source
from api.knowledge.embeddings import EMBEDDING_PROFILE
from api.knowledge.markdown import MarkdownDocument
from api.knowledge.metadata import KnowledgeContract, PositiveInt, Text
from api.knowledge.retrieval import (
    DocumentRevision,
    RankedEvidence,
    RetrievalError,
    RetrievalFailure,
    RetrievalRequest,
    RetrievalResult,
    RetrievalScope,
    Retriever,
    is_eligible,
)

type Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
type Count = Annotated[int, Field(strict=True, ge=0)]
type Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class RelevantSection(DocumentRevision):
    heading: Text

    def matches(self, item: RankedEvidence) -> bool:
        location = item.passage.location
        return (
            item.metadata.document_id == self.document_id
            and item.metadata.version == self.version
            and location.kind == "markdown"
            and bool(location.heading_path)
            and location.heading_path[-1] == self.heading
        )


class RetrievalCase(KnowledgeContract):
    case_id: Text
    query: Text
    scope: RetrievalScope
    service_code: Text | None = None
    acceptable: Annotated[tuple[RelevantSection, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_targets(self) -> Self:
        keys = [
            (item.document_id, item.version, item.heading) for item in self.acceptable
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("Acceptable sections must be unique")
        return self


class RetrievalCaseSet(KnowledgeContract):
    version: Text
    top_k: Annotated[int, Field(strict=True, ge=1, le=20)]
    cases: Annotated[tuple[RetrievalCase, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        identities = [case.case_id for case in self.cases]
        if len(identities) != len(set(identities)):
            raise ValueError("Evaluation case IDs must be unique")
        return self


class CorpusRevision(DocumentRevision):
    content_hash: Hash
    metadata_hash: Hash


class CaseEvaluation(KnowledgeContract):
    case: RetrievalCase
    evidence: tuple[RankedEvidence, ...] = ()
    failure: RetrievalFailure | None = None
    hit: bool | None = None
    first_relevant_rank: PositiveInt | None = None
    reciprocal_rank: Fraction | None = None
    listed_section_coverage: Fraction | None = None
    exclusion_violations: Count | None = None
    duplicate_chunks: Count | None = None

    @model_validator(mode="after")
    def separate_failure_from_empty(self) -> Self:
        if self.failure is not None:
            if self.evidence or any(
                value is not None
                for value in (
                    self.hit,
                    self.first_relevant_rank,
                    self.reciprocal_rank,
                    self.listed_section_coverage,
                )
            ):
                raise ValueError(
                    "Failed cases cannot contain evidence or relevance metrics"
                )
        elif any(
            value is None
            for value in (
                self.hit,
                self.reciprocal_rank,
                self.listed_section_coverage,
                self.exclusion_violations,
                self.duplicate_chunks,
            )
        ):
            raise ValueError("Successful cases require measurements")
        return self


class EvaluationReport(KnowledgeContract):
    case_set_version: Text
    run_mode: Literal["fixture", "live"]
    generated_at: datetime
    embedding_profile: Text
    chunk_strategy: Text = CHUNK_STRATEGY
    chunk_strategy_version: Text = CHUNK_STRATEGY_VERSION
    top_k: PositiveInt
    corpus: tuple[CorpusRevision, ...]
    cases: tuple[CaseEvaluation, ...]
    successful_cases: Count
    failed_cases: Count
    hit_rate_successful_cases: Fraction | None
    mean_reciprocal_rank_successful_cases: Fraction | None
    mean_listed_section_coverage_successful_cases: Fraction | None
    observed_exclusion_violations: Count
    observed_duplicate_chunks: Count
    uninspected_cases: Count


def load_cases(path: Path) -> RetrievalCaseSet:
    return RetrievalCaseSet.model_validate_json(path.read_bytes())


def validate_cases_for_corpus(
    case_set: RetrievalCaseSet, sources: tuple[MarkdownDocument, ...]
) -> None:
    sources = tuple(MarkdownDocument.model_validate(source) for source in sources)
    active = tuple(
        DocumentRevision(
            document_id=doc.metadata.document_id, version=doc.metadata.version
        )
        for doc in sources
    )
    for source in sources:
        verify_source(source)
    for case in case_set.cases:
        request = RetrievalRequest(
            query=case.query,
            scope=case.scope,
            service_code=case.service_code,
            active_revisions=active,
            top_k=case_set.top_k,
        )
        for target in case.acceptable:
            matching = [
                doc
                for doc in sources
                if (doc.metadata.document_id, doc.metadata.version)
                == (target.document_id, target.version)
            ]
            if len(matching) != 1 or not is_eligible(matching[0].metadata, request):
                raise ValueError(
                    "Evaluation target must select an eligible active revision"
                )
            count = sum(
                section.location.location.kind == "markdown"
                and bool(section.location.location.heading_path)
                and section.location.location.heading_path[-1] == target.heading
                for section in matching[0].sections
            )
            if count != 1:
                raise ValueError("Evaluation target heading must resolve unambiguously")


def measure_result(
    case: RetrievalCase,
    request: RetrievalRequest,
    response: RetrievalResult,
    *,
    run_mode: Literal["fixture", "live"],
) -> CaseEvaluation:
    try:
        # Inspect individually validated evidence to count violations before rejecting
        # the response. Never serialize rejected evidence, including internal text.
        items = tuple(RankedEvidence.model_validate(item) for item in response.evidence)
        violations = sum(not is_eligible(item.metadata, request) for item in items)
        duplicates = len(items) - len({item.chunk_id for item in items})
        if violations or duplicates or len(items) > request.top_k:
            return CaseEvaluation(
                case=case,
                failure=RetrievalFailure.INVALID_RESPONSE,
                exclusion_violations=violations,
                duplicate_chunks=duplicates,
            )
        response = RetrievalResult.model_validate(response)
        if run_mode == "live" and any(
            item.score_metric != "cosine_similarity" for item in items
        ):
            return CaseEvaluation(
                case=case,
                failure=RetrievalFailure.INVALID_RESPONSE,
                exclusion_violations=0,
                duplicate_chunks=0,
            )
    except (ValidationError, AttributeError, TypeError):
        return CaseEvaluation(case=case, failure=RetrievalFailure.INVALID_RESPONSE)
    hits = [
        item.rank
        for item in response.evidence
        if any(target.matches(item) for target in case.acceptable)
    ]
    covered = sum(
        any(target.matches(item) for item in response.evidence)
        for target in case.acceptable
    )
    first = min(hits) if hits else None
    return CaseEvaluation(
        case=case,
        evidence=response.evidence,
        hit=bool(hits),
        first_relevant_rank=first,
        reciprocal_rank=1 / first if first else 0,
        listed_section_coverage=covered / len(case.acceptable),
        exclusion_violations=0,
        duplicate_chunks=0,
    )


async def evaluate_retrieval(
    retriever: Retriever,
    case_set: RetrievalCaseSet,
    sources: tuple[MarkdownDocument, ...],
    *,
    embedding_profile: str,
    run_mode: Literal["fixture", "live"] = "fixture",
) -> EvaluationReport:
    case_set = RetrievalCaseSet.model_validate(case_set)
    if run_mode == "live" and embedding_profile != EMBEDDING_PROFILE:
        raise ValueError("Live evaluation requires the approved provider profile")
    validate_cases_for_corpus(case_set, sources)
    active = tuple(
        DocumentRevision(
            document_id=doc.metadata.document_id, version=doc.metadata.version
        )
        for doc in sources
    )
    results: list[CaseEvaluation] = []
    for case in case_set.cases:
        request = RetrievalRequest(
            query=case.query,
            scope=case.scope,
            service_code=case.service_code,
            active_revisions=active,
            top_k=case_set.top_k,
        )
        try:
            result = await retriever.search(request)
            results.append(measure_result(case, request, result, run_mode=run_mode))
        except RetrievalError as error:
            results.append(CaseEvaluation(case=case, failure=error.reason))
        except TimeoutError:
            results.append(CaseEvaluation(case=case, failure=RetrievalFailure.TIMEOUT))
        except Exception:
            results.append(
                CaseEvaluation(case=case, failure=RetrievalFailure.UNAVAILABLE)
            )
    successful = [result for result in results if result.failure is None]
    denominator = len(successful)
    return EvaluationReport(
        case_set_version=case_set.version,
        run_mode=run_mode,
        generated_at=datetime.now(UTC),
        embedding_profile=embedding_profile,
        top_k=case_set.top_k,
        corpus=tuple(
            CorpusRevision(
                document_id=doc.metadata.document_id,
                version=doc.metadata.version,
                content_hash=doc.content_hash,
                metadata_hash=doc.metadata_hash,
            )
            for doc in sources
        ),
        cases=tuple(results),
        successful_cases=denominator,
        failed_cases=len(results) - denominator,
        hit_rate_successful_cases=sum(bool(result.hit) for result in successful)
        / denominator
        if denominator
        else None,
        mean_reciprocal_rank_successful_cases=sum(
            result.reciprocal_rank or 0 for result in successful
        )
        / denominator
        if denominator
        else None,
        mean_listed_section_coverage_successful_cases=sum(
            result.listed_section_coverage or 0 for result in successful
        )
        / denominator
        if denominator
        else None,
        observed_exclusion_violations=sum(
            result.exclusion_violations or 0 for result in results
        ),
        observed_duplicate_chunks=sum(
            result.duplicate_chunks or 0 for result in results
        ),
        uninspected_cases=sum(
            result.exclusion_violations is None or result.duplicate_chunks is None
            for result in results
        ),
    )
