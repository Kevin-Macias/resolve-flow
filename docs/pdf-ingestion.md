# PDF ingestion (RF-404)

Status: PLANNED. Kevin deferred RF-404 beyond the MVP. The proposal below
awaits review and implementation.

## Goal

Extend the existing ingestion flow to text-based PDF documents while keeping
the approved manifest, immutable revisions, hashes, and atomic batch behavior.
Unlike Markdown headings and lines, PDF source locations identify a one-based
page number bound to a document ID and version.

## Proposed behavior

| Input | Result |
| --- | --- |
| Readable text PDF | Extract text separately for each page and retain its original page number |
| Empty or image-only page | Retain an explicit no-text page result; never renumber later pages |
| Document with no extractable text | Reject with a typed no-text failure; do not store an empty knowledge source |
| Corrupt, encrypted, or failed extraction | Reject with a typed failure and leave the batch unchanged |
| Page with a simple table | Preserve layout-oriented text as an approximation; do not claim structured cells or guaranteed reading order |
| Identical revision ingested again | Unchanged, using the same content/metadata hash rules as Markdown |

No-text pages may be blank or scanned images. Garbled nonempty text can pass
automatic checks, so fixtures and manual review must cover extraction quality.

## Implementation proposal

Use a maintained PDF text parser, with extraction behind a small injectable
boundary so failures can be tested offline. Keep PDF page records separate from
Markdown sections. Generalize the store to accept either typed document record,
and dispatch by the manifest source extension.

Add small deterministic PDF fixtures for readable text, an empty page between
text pages, a simple table, and unreadable/encrypted input. Use an issue-report
guide as the sample content. These are ingestion fixtures; do not introduce a
new product feature or broaden the approved retrieval corpus without review.

OCR, recovery of arbitrary damaged files, and reliable extraction of complex
table cells are outside this ticket. Page citations remain valid even when text
layout is approximate; they do not prove extraction fidelity.

## Verification

Test page numbering, document/version binding, empty and all-no-text outcomes,
typed extraction failures, table text preservation on a known fixture, repeat
ingestion, revision conflicts, and rollback of mixed Markdown/PDF batches.
Run existing Markdown tests to preserve their behavior.

Before implementation, approve rejection of all-no-text documents, exclusion
of OCR, and approximate table text.
