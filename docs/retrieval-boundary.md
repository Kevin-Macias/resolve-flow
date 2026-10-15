# Retrieval boundary (RF-407)

Status: DONE. Kevin approved the contract and completed the final PAIR review
on 2026-10-06. All 108 non-database knowledge tests, strict API type checks,
and knowledge lint/format checks passed.

## Goal and scope

Provide an application-owned asynchronous interface that accepts a search
request and returns ranked, typed evidence. Domain contracts must not import
LangChain, SQLAlchemy, pgvector, or an embedding SDK.

RF-407 supplies contracts and an offline fake. RF-408's
[retrieval integration](retrieval-integration.md) adds embeddings, search, and
chunk persistence, tested with deterministic vectors. Live search quality is
unverified. RF-506 adds separate [support evidence operations](evidence-panel.md);
automatic customer workflow retrieval remains unimplemented.

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

Trusted application code supplies scope and active revisions after establishing
permissions. Query text and model output cannot choose access. Endpoint identity
resolution remains separate work.

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

Tests cover request/results, metadata/location matching, ranks/ties, duplicates,
limits, empty results, and typed failures. Fake-adapter tests check active
revisions, status, service, and account/internal access. RF-410 evaluates semantic
relevance.

## Approved choices

Kevin approved the contracts and offline fake before semantic search integration,
the eligibility rules above, and `top_k=5` with a range of 1–20. A relevance
threshold requires evaluation first.

## Implementation and review

`api/knowledge/retrieval.py` defines immutable Pydantic contracts, an async
`Retriever` protocol, shared eligibility checks, typed failures, and a
`RetrievalService` that checks adapter responses. Consumers should call the
service so oversized, unauthorized, malformed, duplicate, or incorrectly
ranked results fail closed. Adapter filtering must still happen before ranking
and limiting: response validation cannot establish that omitted candidates
were ranked correctly.

`api/knowledge/fake_retriever.py` filters candidates and ranks fixed `fixture`
scores, independently of query meaning. Measured adapters use `cosine_similarity`;
each result uses one metric. Ties use chunk UUID strings; passage whitespace
is preserved.

An empty active revision selection returns no sources. A selection cannot
activate multiple versions of the same document. Permissions are explicit,
immutable scope values and are never inferred from query instructions. There
is no authentication or read endpoint in this change.

Kevin's final review covered exclusion of superseded and inactive sources,
filtering before the limit, internal access without access to all accounts,
empty results versus failure, and fixture scores versus real similarity.
