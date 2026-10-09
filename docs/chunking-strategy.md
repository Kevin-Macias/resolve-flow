# Chunking strategy comparison

RF-406 (PAIR). Kevin approved this strategy on 2026-10-06.

A chunk is the passage we embed and later retrieve. Its boundaries determine
which statements travel together as evidence. Document metadata and source
locations remain attached so a passage can be filtered and cited.

## Comparison on the current corpus

The eight Markdown sources contain 1,448 whitespace-separated words. This
comparison uses the exact ingested source text, including headings and editorial
metadata. The fixed baseline groups consecutive words into blocks of at most
100 words, independently for each document, with no overlap. The heading baseline
uses the existing Markdown parser's section boundaries.

| Source | Fixed chunks | Heading sections | Fixed chunks crossing a section boundary |
| --- | ---: | ---: | ---: |
| Account visibility | 2 | 5 | 2 |
| Affected service update | 2 | 4 | 1 |
| Archived report | 3 | 5 | 2 |
| Legacy visibility | 2 | 4 | 1 |
| Missing report help | 2 | 4 | 1 |
| Submission validation | 3 | 5 | 2 |
| Resolved archived report | 2 | 6 | 2 |
| Unresolved submission | 2 | 6 | 2 |
| Total | 18 | 39 | 13 |

There are eight introductory sections containing only the document title and
editorial metadata. Excluding those leaves 31 substantive sections. The longest
section is 96 words, including its heading.

Fixed splitting provides predictable passage sizes and works without headings.
Here it sometimes cuts sentences and combines parts of checks, interpretation,
and limitations. Heading splitting preserves those authored boundaries but
produces smaller passages with different lengths. A section can still depend
on context elsewhere in its document.

These are structural measurements, not retrieval relevance scores. The
100-word baseline is a comparison parameter, not an approved production limit.
RF-410 will evaluate retrieval behavior using reviewed expectations.

## Approved decision

Use one substantive Markdown section per chunk for the current corpus, without
overlap. Keep the exact section text and its existing heading path and line
range; carry the document title and validated manifest metadata alongside it.
Do not create searchable passages from the eight title-and-metadata-only
introductions. Substantive introductory prose in future documents must be
retained rather than discarded merely because it appears before a heading.

For example, the archived-report Checks section stays together, including the
warning that HTTP 404 does not confirm archival and the limitation of the planned
support lookup. Its Interpretation and Next steps sections remain separate
passages with their own citations.

The superseded legacy guide illustrates a remaining dependency: its Historical
advice section must retain the document's superseded and fictional metadata.
Chunk boundaries alone cannot establish applicability or authorization.
Retrieval filtering and the treatment of stale sources remain decisions for
the retrieval tickets.

This selection covers the current short Markdown corpus. Before accepting
longer sections, choose and verify a bounded splitting fallback and embedding
input budget. No fixed production size, tokenizer, overlap for long sections,
or retrieval ranking policy is selected by this decision.

## Implementation boundary

The existing section parser and PostgreSQL chunk schema support this approach.
RF-406 records the reviewed selection; creating and persisting retrieval chunks
belongs with the retrieval implementation. This comparison does not generate
embeddings or make provider calls.
