"""Eligibility, citation provenance, structural analysis, and RF-410 measurements."""

from pathlib import Path

from pydantic import TypeAdapter

from api.evaluations.contracts import Case, CaseSet, Values, observations
from api.evaluations.evidence import load_sources, request_for
from api.evaluations.metric_contracts import Checks, RetrievalMeasurement
from api.knowledge.citations import verify_evidence_catalog
from api.knowledge.evaluation import RelevantSection, RetrievalCase, measure_result
from api.knowledge.metadata import AccessClass, DocumentStatus
from api.knowledge.retrieval import RankedEvidence, RetrievalResult, is_eligible


def analysis_checks(case: Case, observed: Values, checks: Checks) -> None:
    for key, expected in case.expected.items():
        dimension = (
            "tool_policy"
            if key in ("tool_dispatches", "approval_created")
            else "evidence"
            if key == "source_round_trips_as_data"
            else "structure"
        )
        checks.field(key, dimension, observed, key, expected)


def retrieval_checks(
    case: Case, observed: Values, data: CaseSet, root: Path, checks: Checks
) -> RetrievalMeasurement:
    empty = RetrievalMeasurement(
        relevance_applicable="acceptable_sections" in case.expected
    )
    try:
        fixtures = (
            ("foreign_account",)
            if case.setup["corpus"] == "curated_plus_foreign_fixture"
            else ()
        )
        sources = load_sources(root, data, fixture_names=fixtures)
        request = request_for(case, data, sources)
        raw = observed["retrieval_result"]
        if not isinstance(raw, dict):
            raise ValueError("Missing retrieval observations")
        entries = raw.get("evidence")
        if not isinstance(entries, list):
            raise ValueError("Missing retrieval observations")
        items = tuple(RankedEvidence.model_validate(item) for item in entries)
        acceptable = case.expected.get(
            "acceptable_sections", case.expected.get("returned_sections")
        )
        targets = TypeAdapter(tuple[RelevantSection, ...]).validate_python(acceptable)
        definition = RetrievalCase(
            case_id=case.case_id,
            query=request.query,
            scope=request.scope,
            service_code=request.service_code,
            acceptable=targets,
        )
        # measure_result counts eligibility/duplicates before validating the entire
        # response. Do not discard those observations with an earlier model check.
        response = RetrievalResult.model_construct(evidence=items)
        measured = measure_result(definition, request, response, run_mode="fixture")
        if measured.exclusion_violations is not None:
            checks.compare(
                "exclusion_violations",
                "evidence",
                measured.exclusion_violations,
                case.expected["exclusion_violations"],
            )
            checks.compare(
                "duplicate_chunks",
                "evidence",
                measured.duplicate_chunks,
                case.expected["duplicate_chunks"],
            )
        else:
            checks.record(
                "exclusion_violations",
                "evidence",
                "error",
                reason="Evidence eligibility could not be inspected.",
            )
            checks.record(
                "duplicate_chunks",
                "evidence",
                "error",
                reason="Evidence identities could not be inspected.",
            )
        valid = measured.failure is None
        checks.record(
            "retrieval_schema", "structure", "pass" if valid else "fail", valid
        )
        if not valid:
            checks.record(
                "citation_integrity",
                "evidence",
                "unmeasured",
                reason="Invalid retrieval result; provenance cannot be certified.",
            )
            return empty.model_copy(
                update=dict(
                    exclusion_violations=measured.exclusion_violations,
                    duplicate_chunks=measured.duplicate_chunks,
                )
            )
        try:
            verify_evidence_catalog(request, response, sources)
        except ValueError:
            checks.record(
                "citation_integrity",
                "evidence",
                "fail",
                False,
                reason="Evidence does not match permitted source content and provenance.",
            )
            return empty.model_copy(
                update=dict(
                    exclusion_violations=measured.exclusion_violations,
                    duplicate_chunks=measured.duplicate_chunks,
                )
            )
        checks.record("citation_integrity", "evidence", "pass", True)
        sections = observations(
            dict(
                sections=[
                    dict(
                        document_id=item.metadata.document_id,
                        version=item.metadata.version,
                        heading=item.passage.location.heading_path[-1]
                        if item.passage.location.kind == "markdown"
                        else None,
                    )
                    for item in items
                ]
            )
        )["sections"]
        if "returned_sections" in case.expected:
            checks.compare(
                "returned_sections",
                "evidence",
                sections,
                case.expected["returned_sections"],
            )
        if "foreign_text_in_result" in case.expected:
            foreign = any(
                item.metadata.access_class == AccessClass.CUSTOMER_ACCOUNT
                and not is_eligible(item.metadata, request)
                for item in items
            )
            checks.compare(
                "foreign_text_in_result",
                "evidence",
                foreign,
                case.expected["foreign_text_in_result"],
            )
        if "superseded_text_in_result" in case.expected:
            superseded = any(
                item.metadata.status == DocumentStatus.SUPERSEDED for item in items
            )
            checks.compare(
                "superseded_text_in_result",
                "evidence",
                superseded,
                case.expected["superseded_text_in_result"],
            )
        if "hit_at_5" in case.expected:
            checks.compare(
                "hit_at_5", "evidence", measured.hit, case.expected["hit_at_5"]
            )
        return RetrievalMeasurement(
            successful=True,
            hit=measured.hit if "acceptable_sections" in case.expected else None,
            reciprocal_rank=measured.reciprocal_rank
            if "acceptable_sections" in case.expected
            else None,
            listed_section_coverage=measured.listed_section_coverage
            if "acceptable_sections" in case.expected
            else None,
            exclusion_violations=measured.exclusion_violations,
            duplicate_chunks=measured.duplicate_chunks,
            relevance_applicable="acceptable_sections" in case.expected,
        )
    except (ValueError, TypeError, KeyError, IndexError):
        checks.record(
            "retrieval_observation",
            "evidence",
            "error",
            reason="Required retrieval observations are missing or invalid.",
        )
        return empty
