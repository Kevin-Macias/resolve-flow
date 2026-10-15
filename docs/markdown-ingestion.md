# Markdown ingestion (RF-403)

Status: DONE. Kevin approved the contract and completed the final PAIR review.

## Intended outcome

Read the eight approved sources into validated, versioned records with heading
paths and line locations, ready for chunking and retrieval. Ingestion is offline.

## Implemented boundaries

- `knowledge/manifest.json`: an explicitly maintained list of the eight RF-402
  metadata records. Access class comes from this trusted configuration, not
  inferred from Markdown text. The README is an index, not an ingested source.
- `api/knowledge/markdown.py`: source reading, Markdown parsing, hashes, typed
  results, and typed ingestion failures.
- `api/knowledge/store.py`: a small document-store boundary with an in-memory
  implementation for this ticket. PostgreSQL persistence comes with RF-405.
- `tests/knowledge/`: offline parser, repeat-ingestion, conflict, and failure tests.

RF-403's memory store preserves repeat-ingestion behavior within one process.
Durable storage, endpoints, workflow wiring, and embeddings are later integrations.

## Parsing and source locations

Use markdown-it-py in CommonMark mode with source-line mappings rather than splitting headings
with regular expressions. Support standard Markdown headings, including Setext
headings, and avoid treating heading-like text in fenced code as a real heading.
Preserve source text and one-based inclusive line ranges. Heading sections are
structural records, not a final retrieval chunking strategy (RF-406).

Read UTF-8 source bytes under the configured repository root. Reject missing
files, unsupported extensions, invalid UTF-8, empty/whitespace-only sources, and
paths that resolve outside that root. Validate manifest metadata before reading.
Check duplicate identities and replacement references/cycles before storing.

## Hashing and revisions

`content_hash` is SHA-256 of exact file bytes, including line endings. Hash
canonical validated metadata separately to detect access and applicability changes.

Use `(document_id, version)` as the record identity:

| Input compared with saved record | Result |
| --- | --- |
| New identity/version | Store a new immutable record |
| Same identity/version and identical content/metadata hashes | Return unchanged; create no duplicate |
| Same identity/version but changed content or metadata | Reject with a version conflict; require a new version |
| Same identity with a new version | Retain the old version and add the new one |

The manifest selects versions for ingestion; opaque version strings have no
sortable "newest" meaning. Retrieval uses active configuration and access rules,
not every saved historical revision.

Validate and prepare the entire manifest before committing a batch. If any
source or version conflicts, the batch leaves the store unchanged. The later
database implementation must preserve that transaction contract.

## Verification

Cover real-corpus ingestion and repeat ingestion; exact line excerpts; nested
and Setext headings; fenced-code content; preamble text; Unicode and line endings;
new versions; content and metadata conflicts; manifest duplicates; missing or
cyclic replacements; missing/empty/invalid files; path containment; and batch
rollback. Expected access behavior stays grounded in the approved RF-402 rules.

## Use

Run from the repository root using the API virtual environment and `PYTHONPATH`
set to `apps/api/src`, or invoke from application code:

```python
from pathlib import Path
from api.knowledge.store import InMemoryDocumentStore, ingest_manifest

root = Path.cwd()
store = InMemoryDocumentStore()
first = ingest_manifest(root, root / "knowledge/manifest.json", store)
second = ingest_manifest(root, root / "knowledge/manifest.json", store)
# first: eight created results; second: eight unchanged results
saved = store.get("archived-report", "1")
```

Only manifest-listed files are ingested. Editorial metadata lines inside the
Markdown remain source content; they cannot override manifest access declarations.
The legacy and investigation entries are marked fictional in the manifest.

Document-level headings define sections; quoted/list headings and empty headings
stay in source content. Ingestion preserves text without rendering or execution.
It assumes trusted files remain stable while read. Path checks do not defend
against hostile filesystem changes. The synchronous memory store supports one
process without concurrent writers or restart durability.

Parser implementation reference:
[markdown-it-py token stream and line mappings](https://markdown-it-py.readthedocs.io/en/latest/using.html#the-token-stream).

## PAIR review

Kevin approved the trusted manifest, temporary memory store, exact-byte hashing,
and rejection of changed existing versions. Kevin reviewed the resulting corpus records, line locations, and
repeat-ingestion behavior, and confirmed his understanding of the ingestion flow.

Final checks: 280 Python tests passed and 21 database tests were skipped without
a configured test database. The knowledge subset passed all 74 tests, including
28 ingestion tests. Full API Pyright, formatting, lint, lockfile consistency,
relative document links, and whitespace checks passed. No live model calls ran.
