"""Use prepared source sections, the checked retriever, and citation validators."""

import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from api.evaluations.contracts import Case, CaseSet, Values, observations
from api.knowledge.chunks import prepare_chunks
from api.knowledge.evidence_analysis import (
    INSTRUCTIONS,
    InvalidAnalysisOutput,
    build_evidence_analysis_input,
    validate_evidence_analysis_output,
)
from api.knowledge.fake_retriever import FakeRetriever
from api.knowledge.markdown import MarkdownDocument, load_manifest, prepare_markdown
from api.knowledge.metadata import DocumentMetadata
from api.knowledge.retrieval import (
    EvidenceCandidate,
    RetrievalRequest,
    RetrievalService,
)


def load_sources(
    root: Path, data: CaseSet, *, fixture_names: tuple[str, ...] = ()
) -> tuple[MarkdownDocument, ...]:
    sources = [
        prepare_markdown(root, item)
        for item in load_manifest(root / data.default_corpus_manifest)
    ]
    for name in fixture_names:
        raw = data.fixture_sources[name]
        metadata = {
            key: value
            for key, value in raw.items()
            if key not in ("content", "content_from")
        }
        if metadata.get("customer_account_id") == "account-b":
            metadata["customer_account_id"] = str(
                uuid5(NAMESPACE_URL, "evaluation:account-b")
            )
        sources.append(
            prepare_markdown(root, DocumentMetadata.model_validate(metadata))
        )
    return tuple(sources)


def request_for(
    case: Case, data: CaseSet, sources: tuple[MarkdownDocument, ...]
) -> RetrievalRequest:
    context = data.contexts[case.trusted_context]
    accounts = context.get("retrieval_customer_accounts", [])
    if not isinstance(accounts, list):
        raise ValueError("Invalid scope")
    return RetrievalRequest.model_validate(
        dict(
            query=case.input["query"],
            scope={
                "allow_internal": context["allow_internal"],
                "customer_account_ids": [
                    str(uuid5(NAMESPACE_URL, f"evaluation:{name}")) for name in accounts
                ],
            },
            service_code=context["service_code"],
            active_revisions=[
                dict(document_id=s.metadata.document_id, version=s.metadata.version)
                for s in sources
            ],
            top_k=case.setup.get("top_k", 5),
        )
    )


def candidate_for(
    sources: tuple[MarkdownDocument, ...], target: object, score: object
) -> EvidenceCandidate:
    if not isinstance(target, dict):
        raise ValueError("Invalid evidence target")
    chunks = [
        chunk
        for source in sources
        for chunk in prepare_chunks(source)
        if chunk.metadata.document_id == target["document_id"]
        and chunk.metadata.version == target["version"]
        and chunk.passage.location.kind == "markdown"
        and chunk.passage.location.heading_path[-1] == target["heading"]
    ]
    if len(chunks) != 1:
        raise ValueError("Evidence target must resolve exactly once")
    chunk = chunks[0]
    return EvidenceCandidate.model_validate(
        dict(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            metadata=chunk.metadata,
            passage=chunk.passage,
            score=score,
            score_metric="fixture",
        )
    )


async def execute_retrieval(case: Case, data: CaseSet, root: Path) -> Values:
    fixtures = (
        ("foreign_account",)
        if case.setup["corpus"] == "curated_plus_foreign_fixture"
        else ()
    )
    sources = load_sources(root, data, fixture_names=fixtures)
    candidates: list[EvidenceCandidate] = []
    entries = case.setup["fixture_candidates"]
    if not isinstance(entries, list):
        raise ValueError("Invalid fixture candidates")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid candidate")
        if "section" in entry:
            target = entry["section"]
        else:
            source = data.fixture_sources[str(entry["fixture_source"])]
            target = dict(
                document_id=source["document_id"],
                version=source["version"],
                heading="Finding",
            )
        candidates.append(candidate_for(sources, target, entry["score"]))
    request = request_for(case, data, sources)
    result = await RetrievalService(FakeRetriever(tuple(candidates))).search(request)
    # Returned passages are reverified before being permitted in an artifact.
    verified = build_evidence_analysis_input(request, result, sources)
    return observations(
        dict(
            evidence=json.loads(verified.input_json)["evidence"],
            returned_sections=[
                dict(
                    document_id=item.metadata.document_id,
                    version=item.metadata.version,
                    heading=item.passage.location.heading_path[-1]
                    if item.passage.location.kind == "markdown"
                    else None,
                )
                for item in result.evidence
            ],
            ranks=[item.rank for item in result.evidence],
            retrieval_result=result.model_dump(mode="json"),
            score_metric="fixture",
            top_k=request.top_k,
        )
    )


async def execute_analysis(case: Case, data: CaseSet, root: Path) -> Values:
    sources = load_sources(root, data, fixture_names=("attack_fixture",))
    fixture = data.fixture_sources["attack_fixture"]
    candidate = candidate_for(
        sources,
        dict(
            document_id=fixture["document_id"],
            version=fixture["version"],
            heading="Finding",
        ),
        1.0,
    )
    request = request_for(case, data, sources)
    result = await RetrievalService(FakeRetriever((candidate,))).search(request)
    value = build_evidence_analysis_input(request, result, sources)
    payload = json.loads(value.input_json)
    rejected = False
    published = 0
    try:
        report = validate_evidence_analysis_output(
            json.dumps(case.setup["provider_output"]), request, result, sources
        )
    except InvalidAnalysisOutput:
        rejected = True
    else:
        published = len(report.claims)
    return observations(
        dict(
            source_round_trips_as_data=candidate.text
            == payload["evidence"][0]["excerpt"],
            fixed_instructions_unchanged=value.instructions == INSTRUCTIONS,
            output_rejected=rejected,
            published_claims=published,
            approval_created=False,
            tool_dispatches=0,
            policy_id=value.policy_id,
        )
    )
