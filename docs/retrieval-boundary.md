# Retrieval boundary (RF-407)

Status: DONE. Kevin approved the contract and completed the final PAIR review
on 2026-10-06. All 108 non-database knowledge tests, strict API type checks,
and knowledge lint/format checks passed.

## Goal and scope

Provide an application-owned asynchronous interface that accepts a search
request and returns ranked, typed evidence. Domain contracts must not import
LangChain, SQLAlchemy, pgvector, or an embedding SDK.

RF-407 implements the contracts and a deterministic fake adapter for offline
tests. It does not connect retrieval to the workflow or expose an HTTP endpoint.
Production embedding/search adapters and chunk persistence require subsequent
integration work; choosing a fake does not implement semantic search. RF-408 now
provides those adapters in the [retrieval integration](retrieval-integration.md),
tested with deterministic vectors; no live provider search has been verified.

## Approved request

- Nonblank query text and a bounded result count (`top_k`, default 5,
  range 1–20).
- An optional exact service filter. Omitting it allows all services within the
  permitted corpus; it does not broaden authorization.
- An application-established scope: whether internal sources are permitted,
  and the explicit customer account IDs whose sources are permitted. Public
  sources are eligible in every scope. No implicit access to all accounts.
- An explicit active set of document ID/version pairs selected by trusted
  application configuration from the manifest. Stored historical revisions
  are not automatically searchable.

Scope and active revisions are supplied by trusted application code, never
inferred from query text or model output. These structures describe already
established permissions; they do not authenticate a caller or grant permissions.
Endpoint identity resolution remains separate work.

## Approved eligibility and ranking

Apply active-revision, access, service, and current-status restrictions before
ranking and limiting results. Normal diagnosis retrieval excludes superseded
sources. A future historical comparison mode would require a separate reviewed
contract rather than widening the default silently.

Current fictional investigations remain eligible in this demonstration corpus,
with their fictional metadata retained. They can illustrate similar situations
but cannot establish facts about the customer's particular report.

Each result includes chunk identity, exact passage text, validated document
metadata, version-bound source location, rank, and an explicitly named score
metric. Metadata and source location must agree on document ID/version.

For the approved vector profile, use cosine similarity (higher first), with a
stable chunk identity tie-breaker. The score is a similarity measurement, not
a probability or confidence that a diagnosis is correct. Fake scores are
deterministic fixtures, not measured semantic relevance. No minimum relevance
threshold is selected before the retrieval evaluation work.

Return at most `top_k` results, with contiguous ranks starting at 1 and no
duplicate chunk identities. Empty results are a successful search. Multiple
sections from the same document may be returned; document diversity is not
an implicit ranking rule.

## Failures and verification

Invalid requests fail validation. Operational failures use a typed, sanitized
retrieval error and remain distinct from an empty successful result. An invalid
adapter response fails closed rather than passing malformed evidence onward.
Do not include query text, document contents, credentials, or raw provider errors
in failure messages.

Routine tests verify request/result validation, metadata and
location binding, deterministic ranks and ties, duplicate rejection, result
limits, empty results, and typed failures. Fake-adapter eligibility tests
cover active revisions, current status, service, and permitted account/internal
scope against the approved rules. RF-410 owns semantic relevance expectations
and evaluation of the eventual search adapter.

## Approved choices

1. Implement the boundary and offline fake first; integrate actual semantic
   search in the following integration work.
2. Use the eligibility rules above, including exclusion of superseded advice
   and explicit account permissions established by application code.
3. Start with five results, permit 1–20, and defer a relevance threshold until
   it can be evaluated.

## Implementation and review

`api/knowledge/retrieval.py` defines immutable Pydantic contracts, an async
`Retriever` protocol, shared eligibility checks, typed failures, and a
`RetrievalService` that checks adapter responses. Consumers should call the
service so oversized, unauthorized, malformed, duplicate, or incorrectly
ranked results fail closed. Adapter filtering must still happen before ranking
and limiting: response validation cannot establish that omitted candidates
were ranked correctly.

`api/knowledge/fake_retriever.py` filters supplied candidates and ranks their
explicit `fixture` scores. It does not interpret query text, compute embeddings,
or measure semantic relevance. Measured adapters use `cosine_similarity`;
results cannot mix score metrics. Ties use the string form of the chunk UUID.
Passage text retains its original whitespace.

An empty active revision selection returns no sources. A selection cannot
activate multiple versions of the same document. Permissions are explicit,
immutable scope values and are never inferred from query instructions. There
is no authentication or read endpoint in this change.

Kevin's final review covered exclusion of superseded and inactive sources,
filtering before the limit, internal access without access to all accounts,
empty results versus failure, and fixture scores versus real similarity.
