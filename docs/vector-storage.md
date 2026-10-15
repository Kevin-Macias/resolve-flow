# PostgreSQL knowledge storage (RF-405)

Status: DONE. Kevin approved the design and completed the final PAIR review.
The implementation passed all 311 tests and root quality checks.

## Goal and boundaries

RF-405 persists Markdown revisions and provides passage/vector storage through
a migration, ORM models, and an async ingestion adapter. It preserves RF-403's
atomic batches. Chunking, live embeddings, and workflow retrieval are later work;
database tests use deterministic vectors.

## Implemented tables

Use the existing application metadata and migration chain. Keep the knowledge
tables separate from LangGraph's independently managed checkpoint schema.

| Table | Purpose | Important fields and constraints |
| --- | --- | --- |
| `knowledge_documents` | Immutable ingested source revisions | UUID primary key; unique `(document_id, version)`; metadata, original text, content/metadata hashes, parsed sections, ingestion timestamp |
| `knowledge_chunks` | Later searchable passages | UUID primary key; document revision foreign key; chunking strategy/version and ordinal; text and exact source location; unique revision/strategy/version/ordinal |
| `knowledge_embeddings` | Numeric representations of passages | Chunk foreign key; embedding model/profile identifier; `vector(1536)` value; unique chunk/profile |

Persist validated metadata and parsed sections as JSONB to round-trip existing
contracts. Also expose access class, customer account, service, and source status
as constrained columns for later filtering. The write adapter derives them from
the same validated metadata. Access class/account consistency must hold at the
database level. Retrieval authorization remains RF-407/702 work.

The database customer account reference should use the existing account table.
The corpus service label `issue-reports` remains a source classification and
does not require an operational Service row.

Vectors have 1536 dimensions and a profile identifying the model/configuration.
Queries must use a matching profile. Other dimensions require a reviewed schema
change. Selecting storage dimensions does not authorize paid provider calls.

## Index proposal

Start with exact cosine-distance search and ordinary indexes for revision
identities, foreign keys, and future metadata filters. Do not create an
approximate vector index for the eight-source corpus yet.

Exact search provides a reference result for the later retrieval tests. An
approximate HNSW or IVFFlat index trades recall for speed and adds configuration
that this small dataset does not need. Record this as the deliberate RF-405
index choice, and measure before adding an approximate index.

Reference: [pgvector querying and indexes](https://github.com/pgvector/pgvector#indexing).

## Durable ingestion

Use a separate async PostgreSQL adapter for SQLAlchemy, sharing the memory
store's prepared document contracts and result types. Use async database I/O;
avoid running an event loop inside synchronous `commit_batch`.

Within one transaction, insert new revisions and compare hashes for existing
revisions. Identical inputs are unchanged; changed inputs under an existing
version fail and roll back the entire batch. Unique constraints and transactional
conflict handling must also preserve this behavior for concurrent ingestion.
Prior versions remain available after a new revision and across process restarts.

The manifest still selects revisions for the active corpus. Stored historical
rows are not implicitly active sources. This ticket does not create a newest
version rule or an access grant.

## Local database and migration

The current `postgres:17-alpine` image does not provide the pgvector installation
needed by this migration. Compose now selects `pgvector/pgvector:0.8.7-pg17-bookworm`, whose tag was
verified against the official pgvector documentation and pulled successfully. Preserve the existing
named data volume; do not reset the database.

The migration enables `vector` and creates the tables/constraints/indexes.
Downgrade removes this ticket's tables but leaves the database-wide extension
installed so other users of it are unaffected.

## Verification and PAIR decisions

Verify migration upgrade/downgrade; persisted metadata/text/locations; restart
reads; duplicate and changed ingestion; concurrent submissions; batch rollback;
foreign keys and access consistency; embedding dimension/profile uniqueness;
and deterministic exact cosine ordering. Run existing API checks as well.

Kevin approved the three-table structure, 1536 dimensions, exact search without
an approximate index, and the async PostgreSQL adapter. Compatibility was
checked by restoring a backup of the retained local database into an isolated
container with the selected image, then applying the migration there. An online physical backup also started under the new image, with the existing
locale and workflow schema readable. Only then was the local database container
recreated on its retained named volume, migrated, and populated with the corpus.

## Embedding profile recommendation

Approved profile: OpenAI `text-embedding-3-small` with explicit dimensions `1536` and cosine
comparison. The default output size is 1536, which matches the proposed column.
This is a practical starting profile for the small English corpus, not a claim
that retrieval quality has already been evaluated. Keep model/profile identity
with each vector and use the same profile for document and query embeddings.

Prices checked on 2026-10-06 were $0.02 per million input tokens for
`text-embedding-3-small` and $0.13 for `text-embedding-3-large`. Measure baseline
quality before considering a larger model; RF-405 requires storage only.

Sources checked 2026-10-06: [embedding guide](https://developers.openai.com/api/docs/guides/embeddings),
[small model](https://developers.openai.com/api/docs/models/text-embedding-3-small),
and [large model](https://developers.openai.com/api/docs/models/text-embedding-3-large).

Selecting the profile permits designing storage compatible with it. RF-405
still uses deterministic test vectors and makes no live embedding requests.

## Implementation and usage

- `api/knowledge/models.py` defines the three ORM tables. Chunk locations use
  Markdown line ranges; the revision foreign key binds identity/version.
- Migration `0002` enables the public vector extension and installs a frozen SQL
  schema snapshot. Database checks keep indexed policy fields aligned with JSON
  metadata, enforce account scope and foreign keys, and reject zero vectors.
- `PostgresDocumentStore` owns a fresh session/transaction for each batch. It uses
  `ON CONFLICT DO NOTHING`, checks saved hashes, and never overwrites a revision.
  Stable revision ordering avoids opposing lock order across overlapping batches.
- `scripts/ingest_knowledge.py` persists the eight source documents without
  creating chunks or generating embeddings. RF-408 implements those steps in
  a separate opt-in command. The storage adapter is trusted application code and
  is not an authorized customer/support read endpoint.

Ensure `.env` defines `DATABASE_URL` for your local database (see `.env.example`).
With a pgvector-enabled database running, from the repository root:

```bash
uv run --directory apps/api --env-file ../../.env alembic upgrade head
uv run --directory apps/api --env-file ../../.env python scripts/ingest_knowledge.py
```

A second ingestion prints `unchanged` for all eight revisions. Historical versions
remain stored; later retrieval must explicitly select the active corpus and
compatible embedding profile. Database constraints validate structure, not
permission to read sources. Direct privileged SQL can still modify records;
immutable ingestion is an application contract, not a tamper-proof audit ledger.

## Verification

`pnpm check` passed with Node 24.18.1 and the isolated PostgreSQL 17/pgvector
0.8.7 database: formatting, lint, generated-client drift, all type checks, and all
311 tests (none skipped). Ten new integration tests cover durable corpus reads,
a separate-process restart, revision retention, conflicts, concurrent writers,
rollback, database constraints, dimensions, profile uniqueness, exact cosine
ordering, and migration upgrade/downgrade.

`alembic check` found no model/migration drift on the restored test copy. The
actual ingestion command returned eight created results, then eight unchanged
results. A backup of the original database was restored successfully, and the
migration preserved the existing workflow schema in that test copy. No live
embedding requests ran. The disposable validation container is removed after
checks. The local database is now on the pgvector image with migration 0002 and
eight saved documents; its existing named volume and workflow schema were retained.

The image changes from Alpine to Debian while retaining PostgreSQL major 17.
Both logical restore and an online physical backup were verified before the
local switch. This checks this development cluster, not arbitrary external
clusters or collation-dependent datasets. Backups are retained in the protected
`/tmp/resolve-flow-rf405-backup/` directory. No existing volume was deleted.

The local `.env` lacked `DATABASE_URL`; local rollout used the container's
configured connection without printing credentials. Configure that variable
before invoking the documented commands directly.
