# Retrieval tests (RF-410)

Status: DONE. Kevin approved the cases and measurements on 2026-10-08 and
completed implementation review on 2026-10-09. At his request, the ticket closes
with the evaluator and mechanical coverage complete; the live baseline is deferred.
Provider relevance remains unmeasured.
The final `pnpm check` passed with Node 24.18.1: formatting, lint, generated-client
drift, all type checks, and all 428 tests with no skips. Twenty-two new evaluator
tests and two PostgreSQL checks supplement the existing retrieval coverage.
The disposable PostgreSQL 17/pgvector test database was removed after verification.

## Goal

Measure whether search returns useful evidence in its top results, preserves
eligibility rules, and behaves correctly with duplicates and empty results.
Keep mechanical correctness distinct from actual embedding relevance.

RF-410 reuses RF-407/408's structural and SQL tests and adds reviewed relevance
cases, metrics, reports, and an opt-in live command. Workflow integration,
diagnosis generation, and Phase 6 evaluations are separate work.

## Approved relevance cases

Use `top_k=5` and the active manifest revisions. All sources below are version
`1`. A case counts as a hit when at least one listed exact section appears in
the returned top five. Kevin approved these relevance labels; they are not
expectations inferred from embedding scores.

| Case | Query | Scope | Acceptable relevant document / sections |
| --- | --- | --- | --- |
| Validation | My submission returned HTTP 422 because my description was only spaces. Was a report created? | Internal support | `submission-validation`: Checks; Interpretation |
| Archive behavior | A report was created successfully, then archived. Why does it disappear from the customer list? | Internal support | `archived-report`: Interpretation; Next steps and limits |
| Account visibility | Can two users in the same customer account see the same reports? What about another account? | Internal support | `account-visibility`: Interpretation; Next steps and limits |
| Service update | What does setting affected_service_code to null do? Can it restore a missing report? | Internal support | `affected-service-update`: Checks and behavior; Limits |
| Uncertain submission | I clicked submit but have no confirmation, error, or report ID. Now I cannot find the report. | Internal support | `unresolved-submission`: Evidence gaps and competing explanations; Current finding; `missing-report-help`: When the outcome is unclear |
| Customer help | I clicked submit but received no confirmation and cannot find my report. What should I tell support? | Public only | `missing-report-help`: What to provide; When the outcome is unclear |

An accepted hit demonstrates relevant general evidence. It does not confirm the
cause of an individual customer's missing report. Fictional investigations remain
explicit fixtures. The uncertain case must not be interpreted as successful
diagnosis of archival, validation failure, or an account mismatch.

Labels list some useful passages, not all. Unlisted results may be relevant,
so these labels cannot support a precision score.

## Approved measurements

- Per-case hit@5: whether an acceptable passage appeared in the top five.
- Per-case reciprocal rank: `1 / rank` for the first acceptable passage, or zero
  when none appeared. Average this as mean reciprocal rank for this case set.
- Coverage of the declared acceptable sections: fraction retrieved, labeled as
  coverage of the listed alternatives rather than exhaustive semantic recall.
- Exclusion violations: count ineligible returned results independently of the
  relevance metrics. Duplicate chunk identities are also reported independently.

Record case-set version, manifest metadata/content hashes, embedding profile,
chunking strategy/version, top-k, actual returned passages/ranks/scores, failures,
and aggregate metrics. Operational failures must be reported as failures rather
than quietly turned into empty successful searches. Empty successful searches
have a zero hit and reciprocal rank for cases with expected relevant passages.

Aggregate relevance metrics use successful cases as their explicit denominator,
and report the number of failed cases separately. If every case fails, quality
metrics are null. A baseline with failures is incomplete, regardless of its
success-only averages. Violation totals are labeled as observed counts;
`uninspected_cases` identifies searches whose violations could not be measured,
such as timeouts or malformed evidence. Zero observed violations with failed
searches does not certify exclusion correctness.

Do not choose a similarity cutoff or aggregate quality gate before inspecting
the actual baseline. Mechanical eligibility rules require zero violations.
Later changes can be compared using the same reviewed case set and corpus.

## Mechanical scenarios

Run ordinary offline tests for metric arithmetic and report serialization using
explicit rankings. They verify the evaluator, not semantic retrieval quality.
Use PostgreSQL with deterministic vectors to verify pre-limit access, service,
active revision, status, profile, and strategy filters; stable ties; no duplicate
chunk identities; multiple sections per document; and an empty filtered result.
Reuse existing tests where they already demonstrate a behavior instead of
duplicating them.

In particular, the superseded legacy guide must never appear in normal diagnosis
retrieval even when a deterministic test assigns it the closest vector. Public
scope must exclude internal/account sources; internal permission alone must
not authorize all customer accounts.

## Live baseline boundary

Provide an explicit opt-in command to run the reviewed queries against already
indexed provider vectors. It requires a database connection and provider key.
Verify the corpus/profile/strategy is completely indexed before measuring;
missing indexing is a setup error, not a successful zero-relevance baseline.
The evaluation command must not silently create embeddings for documents or
change existing source data.

The command embeds queries and may incur charges. Implementation and ordinary
tests stay offline. A live baseline needs a separate decision after review;
until then, report provider relevance as unmeasured.

## Completion and ownership

Kevin approved the relevance labels and metrics before implementation and
requested completion after review on 2026-10-09. Completion covers the offline
evaluator and mechanical tests. Provider relevance requires the deferred live
baseline; synthetic ranks measure only evaluator behavior.

## Implementation and review

- `knowledge/evaluations/retrieval-v1.json` stores the six approved queries,
  scopes, acceptable document/version/headings, and result count. Labels must
  resolve to exactly one eligible section in the active corpus before a run.
- `api/knowledge/evaluation.py` measures hit, first relevant rank, reciprocal
  rank, coverage of the listed alternatives, and observed violations. Rejected
  evidence is not serialized, including unauthorized internal passage text.
  Reports retain the actual successful results, full cases, corpus hashes,
  profile, strategy/version, timestamp, and explicit fixture/live mode.
- `verify_indexed_corpus` reads the saved revisions, exact prepared chunks, and
  vectors of the selected profile without changing them. Missing, extra,
  mismatched, or incompatible indexing fails before provider construction.
- `scripts/evaluate_retrieval.py` requires `--live`, then performs preflight and
  only embeds queries. It can print JSON or write a new local report file;
  existing reports are not overwritten. A case failure or observed eligibility/
  duplicate violation gives a nonzero exit status. No aggregate relevance gate
  has been invented.

After reviewing this implementation and explicitly choosing to run the live
baseline, configure `DATABASE_URL` and `OPENAI_API_KEY`. If the approved corpus
has no provider vectors yet, indexing is a separate paid opt-in operation:

```bash
uv run --directory apps/api --env-file ../../.env python scripts/index_knowledge.py --live
uv run --directory apps/api --env-file ../../.env python scripts/evaluate_retrieval.py --live --output /tmp/resolve-flow-retrieval-baseline-v1.json
```

These commands were not run during implementation. The first run needs all
31 corpus chunks indexed under the approved provider profile, including the
superseded fixture that search must exclude. Existing tests use distinct test
profiles and cannot satisfy this preflight. Read-only preflight and empty
filtered search are verified against a disposable database; existing tests
continue to cover scope/status/revision/profile/strategy filtering, duplicates,
ties, and transaction/concurrency behavior.

The deferred live baseline requires separate authorization and review before
claiming measured provider retrieval quality.
