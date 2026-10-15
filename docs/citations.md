# Verifiable citations (RF-409)

Status: DONE. Kevin approved the contract and completed the final PAIR review
on 2026-10-08.
The final `pnpm check` passed: formatting, lint, generated-client drift, all
type checks, and 366 offline tests, including 38 citation tests. The 38 existing
database tests were skipped because `TEST_DATABASE_URL` was not configured.

## Goal and boundary

RF-409 links typed claims to verified source passages and returns a structured
report. Citations establish provenance; human review checks whether evidence
supports the claim. RF-506 reuses this boundary in separate
[support evidence operations](evidence-panel.md). Automatic workflow retrieval
and customer diagnosis endpoints remain separate integrations. The preliminary
workflow diagnosis stays unchanged.

## Approved claim categories

| Category | Meaning | Required references |
| --- | --- | --- |
| Supported | The cited passage directly supports the statement | At least one supporting passage |
| Inference | An interpretation drawn from cited evidence, with reasoning stated explicitly | At least one supporting passage and an explanation |
| Missing evidence | Information needed to establish a conclusion is unavailable | An explanation of what is missing; references to documented limitations are optional |
| Conflict | Available evidence points in opposing directions | Supporting and contradicting references, plus an explanation of the disagreement |

The caller assigns categories for human review. Validation checks structure;
semantic support requires review regardless of retrieval score.

A missing-evidence claim reports an unresolved gap. An empty search result is not
proof that a fact or document does not exist. A documented system limitation
may be cited without implying it proves an individual report's state.

References identify a retrieved chunk and its relationship to the claim
(`supports` or `contradicts`). Duplicate chunk/relationship pairs are rejected.
A conflict may refer to different passages from one document or from different
documents; it does not require two independent sources. If a single passage
contains opposing statements, it may be referenced in both roles, with the
disagreement explained explicitly.
Supported claims and missing-evidence claims do not accept contradicting
references. Inferences may retain opposing evidence as part of their explicit
reasoning; conflict claims require both roles.

## Implemented citation assembly

The caller supplies claims referencing chunk IDs, a checked retrieval result,
the trusted retrieval request/scope, and the corresponding loaded Markdown
source revisions. Citation assembly does the following:

1. Recheck result eligibility within the supplied active revisions and access
   scope. References must resolve to that supplied evidence set; the caller
   cannot introduce an arbitrary file path, version, location, or quotation.
2. Match evidence metadata to the loaded source revision and verify its content
   and metadata hashes. Loaded source revisions come from trusted application
   storage/configuration, not model output.
3. Verify the cited passage's heading path, line range, and exact text against
   the source parser. Reject invented text, altered locations, and mismatched
   revisions rather than silently repairing or dropping them.
4. Build immutable citation snapshots with chunk ID, document ID/version, title,
   source path, heading path, line range, exact excerpt, source hashes, and
   source metadata including access, status, and fictional flags.
5. Return claims with their explicit category, reasoning where required, and
   supporting/contradicting citations. Stable citation identities bind the
   chunk and source revision hashes, independent of retrieval rank.

Use the entire verified chunk as the citation excerpt initially. Selecting
smaller quotations or subranges would require a separate validation rule.
Snapshots retain versioned evidence even if later retrieval selects a newer
revision. Re-displaying saved internal evidence requires current access checks;
the snapshot itself is not an access grant or a public response.

An unknown reference, unauthorized result, unavailable source revision, or
source mismatch fails the assembly with a typed sanitized error. Empty claims
and empty evidence may produce an empty successful result. A missing-evidence
claim can stand alone without fabricating a citation.

## Example for review

- **Supported:** "Archived reports are excluded from customer reads." Cite the
  archived-report Interpretation section.
- **Inference:** "Archival is one possible explanation for the missing report."
  Cite the same section and explain that HTTP 404 also has other possible causes.
- **Missing evidence:** "The current state of this report has not been
  independently verified." Explain the unavailable authorized lookup; optionally
  cite the runbook's Checks section documenting that limitation.
- **Conflict:** Show the passages making opposing statements and keep the
  disagreement explicit. Superseded historical advice remains excluded by
  normal retrieval policy; RF-409 does not widen source eligibility to create
  a conflict example.

The claim "This customer's report was archived" cannot be justified by general
runbook behavior or a fictional similar investigation. Semantic correctness
remains a reviewed expectation, with evaluation work following separately.

## Implementation and verification

The contracts and assembler are in `api/knowledge/citations.py`, with
offline tests using reviewed sources and deterministic evidence. Tests cover
required claim/reference relationships, unknown and duplicate references,
source hashes, exact excerpts and locations, revision binding, access checks,
stable identities, fictional metadata, empty results, and sanitized errors.
Kevin completed the final PAIR review; RF-409 is DONE.

`ClaimDraft` contains a statement, explicit category, explanation, and chunk/role
references. `assemble_citations` checks the request/result, resolves references
against supplied trusted source revisions, and returns a `CitationReport`.
Each `CitedClaim` retains its draft and attributed `Citation` snapshots. Repeated
references across claims reuse the same citation identity; the same chunk may
play opposing roles in a conflict. Duplicate claim IDs are rejected.

`format_citation_location` produces a plain text title, document ID/version,
heading path, and line range. Structured snapshots preserve source paths and
metadata; no generated web URL, Markdown rendering, or customer projection is
introduced. The assembler requires matching parsed sections, so arbitrary
subranges and PDF evidence cannot be assembled in this Markdown-only slice.

Hashes detect mismatches with supplied revisions; trusted storage/configuration
must remain secure. Use trusted source inputs and review whether each claim
follows from its evidence.
