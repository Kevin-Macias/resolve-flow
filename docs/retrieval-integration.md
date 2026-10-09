# Retrieval integration (RF-408)

Status: DONE. Kevin approved the scope on 2026-10-06 and completed the final PAIR
review on 2026-10-08. No live embedding requests have run.
The final `pnpm check` passed with Node 24.18.1: lint, formatting, generated-client
drift, frontend/API/client types, and all 366 tests with no skips. Database tests
used a disposable PostgreSQL 17/pgvector 0.8.7 instance, removed after checks.

## Selected LangChain value

Use `langchain-openai`'s `OpenAIEmbeddings` behind an application-owned embedding
interface. Its document/query methods and async implementations give us a
consistent provider integration point. Validate returned vectors in application
code: dimensions, finite values, nonzero norm, count, and profile compatibility.
Provider exceptions must become sanitized typed failures.

The approved profile remains `openai:text-embedding-3-small:1536:v1`. Explicitly
configure the model and dimensions; never compare vectors from different
profiles. Deterministic test embeddings remain separate from this profile.

This adds a dependency and another layer over the OpenAI SDK. The documented
value is the embedding integration and its reusable document/query interface;
it does not improve retrieval quality by itself. Existing direct extraction
integration remains separate.

The LangChain PGVectorStore documentation describes configuring a table with
content, embedding, and metadata columns. Our storage separates revisions,
chunks, and profile-specific embeddings across three tables. Application-owned
SQLAlchemy queries fit those joins and the reviewed filters directly. Keep
that implementation rather than adding a second vector-store schema or a view
with a separate write lifecycle.

Domain request/evidence contracts remain independent of LangChain. The existing
CommonMark parser supplies exact heading sections and source locations; no
LangChain document loader or splitter is needed for this corpus. No agent,
model-generated filter, or retrieval chain is introduced.

## Implemented scope

1. Prepare the approved heading-aware chunks from validated Markdown revisions.
   Preserve exact passage text and locations. Skip title-and-editorial-only
   introductions using an explicit corpus rule, retaining substantive preambles.
   Record a chunking strategy/version and deterministic chunk identities.
2. Add an application-owned async embedding interface, a LangChain provider
   adapter, and deterministic test implementations. Embed document title plus
   exact section text; embed query text through the matching profile.
3. Persist chunks and vectors idempotently in the existing tables. Prepare and
   validate an embedding batch before its database writes; retrying identical
   preparation must not duplicate or overwrite chunk content. Provider failure
   must not leave a partially written batch.
4. Implement a PostgreSQL `Retriever` adapter. Apply active revisions, current
   status, service, access scope, chunking strategy/version, and embedding profile
   restrictions before ordering and limiting. Use exact cosine distance,
   converting it to cosine similarity for the typed result. Preserve the RF-407
   stable chunk identity tie-breaker and checked service boundary.
5. Provide an explicit opt-in indexing command. Ordinary tests make no live
   provider calls. Do not connect the workflow or introduce a retrieval endpoint.

## Approved input size decision

Use a conservative 512-token application budget per embedding input,
including the document title, measured with the selected model's tokenizer.
Do not silently split, truncate, or average an oversized section. Reject it with
a typed preparation error until a longer-section fallback is reviewed.
Apply the same explicit budget to query inputs. The current short corpus should
fit: the 31 prepared passages have a largest embedding input of 127 tokens.
This is an application limit, not a claim about the provider's maximum capacity.

## Verification and completion

Test chunk selection and exact source locations, deterministic identities,
embedding payloads/profile/vector validation, provider error sanitization,
atomic/idempotent persistence, and actual SQL filtering before the result limit.
Use deterministic vectors to verify cosine order, score conversion, ties,
empty results, and incompatible profile/strategy exclusions in PostgreSQL.

RF-410 still owns semantic relevance measurements. Offline ordering tests
validate integration mechanics, not whether real embeddings retrieve the best
evidence. RF-409 still owns citation rendering and claim attribution.

## Sources

Checked 2026-10-06:

- [OpenAIEmbeddings reference](https://reference.langchain.com/python/langchain-openai/embeddings/base/OpenAIEmbeddings)
- [LangChain embedding interfaces](https://docs.langchain.com/oss/python/integrations/embeddings)
- [PGVectorStore integration and table configuration](https://docs.langchain.com/oss/python/integrations/vectorstores/pgvectorstore)
- [OpenAI embedding guide: dimensions and tokenizer](https://developers.openai.com/api/docs/guides/embeddings)

## Implementation map and usage

- `knowledge/chunks.py` prepares exact sections using strategy
  `markdown-heading`, version `1`, and UUID5 identities bound to document
  ID/version, strategy/version, and ordinal. The explicit editorial rule skips
  a section containing only a top-level title and the corpus's single-line
  visibility/version/date banner. Other introductory prose is retained. Section
  text and locations are checked against the original source parser.
- `knowledge/embeddings.py` owns the provider protocol, 512-token budget,
  profile constants, and vector/count validation. `cl100k_base` is selected
  through the model tokenizer mapping. Special token-like source text is counted
  as ordinary text. The first tokenizer use may download its public vocabulary;
  warm its cache before running tests without network access.
- `knowledge/langchain_embeddings.py` configures the approved model/dimensions,
  disables automatic long-input splitting, uses a 30-second timeout and zero
  automatic retries, and translates failures. Its `aclose()` closes owned SDK
  clients; injected clients remain caller-owned.
- `knowledge/postgres_retriever.py` implements `PostgresChunkIndexer` and
  `PostgresRetriever`. Indexing requires existing matching source revisions,
  skips saved embeddings of the requested profile, and prepares all missing
  vectors before one transaction writes passages/vectors. Conflicts roll back
  the batch. Concurrent identical runs preserve the first saved vector.
  Concurrent runs can both incur provider work before one wins the insert;
  idempotent storage does not guarantee avoidance of duplicate provider cost.
- SQL restrictions apply before ordering and limiting. Search converts cosine
  distance to similarity with `1 - distance`, bounds numerical rounding to
  `[-1, 1]`, validates the result, and uses the RF-407 service for access/output
  checks. Oversized query inputs produce typed `invalid_input` failures rather
  than silent truncation. Empty active selections require no embedding call.

After migration, with `DATABASE_URL` and `OPENAI_API_KEY` configured, the following
explicit command creates live provider embeddings and may incur API charges:

```bash
uv run --directory apps/api --env-file ../../.env python scripts/index_knowledge.py --live
```

The command is not run during ordinary tests or this implementation. Without
`--live` it exits before provider/database construction. Repeating unchanged
indexing reuses saved vectors. The development database has its original eight
ingested documents; its chunks and provider vectors were not populated here.
Tests use a disposable database and a separate `test:1536:v1` profile.

For review, follow a prepared section from `prepare_chunks` through indexing,
then inspect `PostgresRetriever.search`: the query's permissions select eligible
rows before the nearest passages are returned. The workflow and endpoints do
not invoke these components yet. Actual provider quality and live compatibility
remain unverified; RF-410 covers semantic relevance evaluation.
