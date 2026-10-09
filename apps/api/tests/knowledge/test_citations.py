from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from api.knowledge.citations import (
    Citation,
    CitationError,
    CitationFailure,
    CitationReport,
    ClaimDraft,
    EvidenceReference,
    EvidenceRole,
    assemble_citations,
    format_citation_location,
)
from api.knowledge.markdown import MarkdownDocument, load_manifest, prepare_markdown
from api.knowledge.retrieval import (
    DocumentRevision,
    RankedEvidence,
    RetrievalRequest,
    RetrievalResult,
    RetrievalScope,
)

ROOT = Path(__file__).resolve().parents[4]


def source(identity: str = "archived-report", **changes: Any) -> MarkdownDocument:
    meta = next(
        m
        for m in load_manifest(ROOT / "knowledge/manifest.json")
        if m.document_id == identity
    )
    return prepare_markdown(ROOT, meta.model_copy(update=changes))


def evidence(
    doc: MarkdownDocument, heading: str = "Interpretation", identity: int = 1
) -> RankedEvidence:
    section = next(
        s
        for s in doc.sections
        if s.location.location.kind == "markdown"
        and s.location.location.heading_path[-1] == heading
    )
    return RankedEvidence(
        chunk_id=UUID(int=identity),
        text=section.text,
        metadata=doc.metadata,
        passage=section.location,
        score=1.0,
        score_metric="fixture",
        rank=1,
    )


def request(*docs: MarkdownDocument, **changes: Any) -> RetrievalRequest:
    return RetrievalRequest.model_validate(
        {
            "query": "Missing report",
            "scope": RetrievalScope(allow_internal=True),
            "active_revisions": tuple(
                DocumentRevision(
                    document_id=doc.metadata.document_id, version=doc.metadata.version
                )
                for doc in docs
            ),
        }
        | changes
    )


def claim(item: RankedEvidence | None = None, **changes: Any) -> ClaimDraft:
    return ClaimDraft.model_validate(
        {
            "claim_id": "archive-behavior",
            "statement": "Archived reports are excluded from customer reads.",
            "kind": "supported",
            "references": (
                EvidenceReference(chunk_id=item.chunk_id, role=EvidenceRole.SUPPORTS),
            )
            if item
            else (),
        }
        | changes
    )


def report(
    doc: MarkdownDocument, item: RankedEvidence, draft: ClaimDraft | None = None
) -> CitationReport:
    return assemble_citations(
        (draft or claim(item),), request(doc), RetrievalResult(evidence=(item,)), (doc,)
    )


def test_source_backed_snapshot_and_structured_roundtrip() -> None:
    doc = source()
    item = evidence(doc)
    result = report(doc, item)
    citation = result.claims[0].citations[0].citation
    assert citation.excerpt == item.text
    assert citation.passage == item.passage
    assert citation.metadata == doc.metadata
    assert citation.content_hash == doc.content_hash
    assert citation.metadata_hash == doc.metadata_hash
    assert result.claims[0].citations[0].role == "supports"
    assert CitationReport.model_validate_json(result.model_dump_json()) == result
    assert "archived-report@1" in format_citation_location(citation)
    assert "Interpretation" in format_citation_location(citation)
    assert "lines" in format_citation_location(citation)


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "supported", "references": ()},
        {"kind": "inference"},
        {"kind": "inference", "references": (), "explanation": "Possible cause"},
        {"kind": "missing_evidence"},
        {"kind": "conflict", "explanation": "Opposing evidence"},
        {"kind": "conflict", "references": (), "explanation": "Opposing evidence"},
        {"statement": " "},
        {"claim_id": " "},
        {"explanation": " "},
        {"kind": "unknown"},
        {"location": "invented.md"},
    ],
)
def test_invalid_claim_categories_and_fields(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        claim(evidence(source()), **changes)


def test_inference_and_standalone_gap_remain_explicit() -> None:
    doc = source()
    item = evidence(doc)
    inference = claim(
        item,
        kind="inference",
        explanation="404 has multiple possible causes; archival is one possibility.",
    )
    gap = claim(
        kind="missing_evidence",
        claim_id="report-state-gap",
        statement="Current state has not been independently verified.",
        explanation="An authorized current-state lookup is unavailable.",
    )
    result = assemble_citations(
        (inference, gap), request(doc), RetrievalResult(evidence=(item,)), (doc,)
    )
    assert [c.draft.kind for c in result.claims] == ["inference", "missing_evidence"]
    assert result.claims[1].citations == ()
    assert (
        assemble_citations((gap,), request(), RetrievalResult(), ()).claims[0].draft
        == gap
    )
    assert assemble_citations((), request(), RetrievalResult(), ()) == CitationReport()
    checks = evidence(doc, "Checks")
    limited = claim(
        checks,
        kind="missing_evidence",
        explanation="The runbook documents the unavailable lookup.",
    )
    assert len(report(doc, checks, limited).claims[0].citations) == 1


def test_conflict_has_explicit_opposing_roles_in_same_passage() -> None:
    doc = source()
    item = evidence(doc)
    refs = (
        EvidenceReference(chunk_id=item.chunk_id, role=EvidenceRole.SUPPORTS),
        EvidenceReference(chunk_id=item.chunk_id, role=EvidenceRole.CONTRADICTS),
    )
    draft = claim(
        item,
        kind="conflict",
        explanation="The caller identifies opposing statements for human review.",
        references=refs,
    )
    resolved = report(doc, item, draft).claims[0]
    assert [c.role for c in resolved.citations] == ["supports", "contradicts"]
    assert resolved.citations[0].citation == resolved.citations[1].citation
    for kind in ("supported", "missing_evidence"):
        with pytest.raises(ValidationError):
            claim(item, kind=kind, explanation="Opposition", references=refs)
    with pytest.raises(ValidationError):
        claim(item, references=(refs[0], refs[0]))


@pytest.mark.parametrize(
    "case", ["unknown", "unavailable", "duplicate_claim", "duplicate_source"]
)
def test_resolution_errors_are_typed_and_sanitized(case: str) -> None:
    doc = source()
    item = evidence(doc)
    drafts = (claim(item),)
    sources = (doc,)
    expected = CitationFailure.INVALID_INPUT
    if case == "unknown":
        drafts = (
            claim(
                item,
                references=(
                    EvidenceReference(chunk_id=uuid4(), role=EvidenceRole.SUPPORTS),
                ),
            ),
        )
        expected = CitationFailure.UNKNOWN_REFERENCE
    elif case == "unavailable":
        sources = ()
        expected = CitationFailure.SOURCE_UNAVAILABLE
    elif case == "duplicate_claim":
        drafts = drafts + drafts
    else:
        sources = sources + sources
    with pytest.raises(CitationError) as error:
        assemble_citations(
            drafts, request(doc), RetrievalResult(evidence=(item,)), sources
        )
    assert error.value.reason == expected
    assert str(error.value) == f"Citation assembly failed: {expected.value}"
    assert doc.text not in str(error.value)


@pytest.mark.parametrize(
    "case",
    [
        "text",
        "lines",
        "heading",
        "metadata",
        "source_text",
        "source_unicode",
        "content_hash",
        "metadata_hash",
        "source_sections",
        "wrong_version",
    ],
)
def test_altered_evidence_or_source_fails_closed(case: str) -> None:
    doc = source()
    item = evidence(doc)
    loaded = doc
    if case == "text":
        item = item.model_copy(update={"text": item.text + "Invented statement."})
    elif case in {"lines", "heading"}:
        location = item.passage.location
        altered = location.model_copy(
            update={"line_end": location.line_end + 1}
            if case == "lines" and location.kind == "markdown"
            else {"heading_path": ("Invented",)}
        )
        item = item.model_copy(
            update={"passage": item.passage.model_copy(update={"location": altered})}
        )
    elif case == "metadata":
        item = item.model_copy(
            update={
                "metadata": item.metadata.model_copy(update={"title": "Invented title"})
            }
        )
    elif case == "source_text":
        loaded = doc.model_copy(update={"text": doc.text + "Invented source."})
    elif case == "source_unicode":
        loaded = doc.model_copy(update={"text": doc.text + "\ud800"})
    elif case in {"content_hash", "metadata_hash"}:
        loaded = doc.model_copy(update={case: "0" * 64})
    elif case == "source_sections":
        loaded = doc.model_copy(update={"sections": ()})
    else:
        loaded = source(version="2")
    with pytest.raises(CitationError) as error:
        assemble_citations(
            (claim(item),), request(doc), RetrievalResult(evidence=(item,)), (loaded,)
        )
    assert error.value.reason == (
        CitationFailure.SOURCE_UNAVAILABLE
        if case == "wrong_version"
        else CitationFailure.SOURCE_MISMATCH
    )


@pytest.mark.parametrize(
    "case", ["internal", "inactive", "service", "stale", "account", "over_limit"]
)
def test_eligibility_rechecked_before_citation(case: str) -> None:
    doc = source()
    scope = RetrievalScope(allow_internal=True)
    changes: dict[str, Any] = {}
    if case == "internal":
        scope = RetrievalScope()
    elif case == "inactive":
        changes["active_revisions"] = ()
    elif case == "service":
        changes["service_code"] = "other-service"
    elif case == "stale":
        doc = source(status="superseded", superseded_by="replacement")
    elif case == "account":
        doc = source(access_class="CUSTOMER_ACCOUNT", customer_account_id=uuid4())
    item = evidence(doc)
    items = (item,)
    if case == "over_limit":
        second = evidence(doc, "Checks", 2).model_copy(update={"rank": 2, "score": 0.5})
        items = (item, second)
        changes["top_k"] = 1
    with pytest.raises(CitationError) as error:
        assemble_citations(
            (claim(item),),
            request(doc, scope=scope, **changes),
            RetrievalResult(evidence=items),
            (doc,),
        )
    assert error.value.reason == CitationFailure.INELIGIBLE_EVIDENCE


def test_permitted_account_and_public_sources() -> None:
    account = uuid4()
    doc = source(access_class="CUSTOMER_ACCOUNT", customer_account_id=account)
    item = evidence(doc)
    result = assemble_citations(
        (claim(item),),
        request(doc, scope=RetrievalScope(customer_account_ids=frozenset({account}))),
        RetrievalResult(evidence=(item,)),
        (doc,),
    )
    assert (
        result.claims[0].citations[0].citation.metadata.customer_account_id == account
    )
    public = source(access_class="PUBLIC")
    item = evidence(public)
    assert assemble_citations(
        (claim(item),),
        request(public, scope=RetrievalScope()),
        RetrievalResult(evidence=(item,)),
        (public,),
    ).claims


def test_identity_ignores_rank_and_is_bound_to_revision_and_hashes() -> None:
    doc = source()
    first = evidence(doc)
    original = report(doc, first).claims[0].citations[0].citation
    second = evidence(doc, "Checks", 2).model_copy(update={"score": 0.9})
    result = assemble_citations(
        (claim(first), claim(second, claim_id="checks")),
        request(doc),
        RetrievalResult(evidence=(first, second.model_copy(update={"rank": 2}))),
        (doc,),
    )
    reranked = assemble_citations(
        (claim(first),),
        request(doc),
        RetrievalResult(
            evidence=(
                second.model_copy(update={"rank": 1, "score": 1.0}),
                first.model_copy(update={"rank": 2, "score": 0.8}),
            )
        ),
        (doc,),
    )
    assert (
        original.citation_id
        == result.claims[0].citations[0].citation.citation_id
        == reranked.claims[0].citations[0].citation.citation_id
    )
    revised = source(version="2")
    assert (
        report(revised, evidence(revised)).claims[0].citations[0].citation.citation_id
        != original.citation_id
    )
    with pytest.raises(ValidationError):
        Citation.model_validate(original.model_dump() | {"citation_id": uuid4()})
    with pytest.raises(ValidationError):
        Citation.model_validate(
            original.model_dump()
            | {"passage": original.passage.model_dump() | {"version": "wrong"}}
        )
    with pytest.raises(ValidationError):
        original.metadata.version = "changed"


def test_fictional_flag_retained_and_unresolved_claims_not_silently_dropped() -> None:
    doc = source(fictional=True)
    item = evidence(doc)
    assert report(doc, item).claims[0].citations[0].citation.metadata.fictional
    wrong = claim(
        item,
        claim_id="unknown",
        references=(EvidenceReference(chunk_id=uuid4(), role=EvidenceRole.SUPPORTS),),
    )
    with pytest.raises(CitationError):
        assemble_citations(
            (claim(item), wrong),
            request(doc),
            RetrievalResult(evidence=(item,)),
            (doc,),
        )


def test_constructed_invalid_input_and_resolved_reference_mismatch() -> None:
    doc = source()
    item = evidence(doc)
    invalid = claim(item).model_copy(update={"statement": " "})
    with pytest.raises(CitationError) as error:
        report(doc, item, invalid)
    assert error.value.reason == CitationFailure.INVALID_INPUT
    claim_result = report(doc, item).claims[0]
    with pytest.raises(ValidationError):
        type(claim_result).model_validate(claim_result.model_dump() | {"citations": ()})
    with pytest.raises(ValidationError):
        CitationReport(claims=(claim_result, claim_result))
