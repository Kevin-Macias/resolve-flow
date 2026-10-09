# ResolveFlow roadmap

This is the shared delivery tracker. Keep detailed implementation discussion in
issues or commits; keep status, ownership, dependencies, and acceptance here.

## Legend

Status:

- `DONE`: implemented and verified
- `NEXT`: the single recommended next learning ticket
- `READY`: sufficiently defined and not blocked by unfinished dependencies
- `PLANNED`: later work or dependent on an earlier phase
- `BLOCKED`: cannot progress; add the reason beside the ticket

Ownership:

- `HAND`: Kevin writes the first design and implementation
- `PAIR`: Kevin owns decisions; AI assists implementation and review
- `DELEGATE`: AI may implement from the ticket contract; Kevin reviews

## Current milestone

**Milestone 5: incident workspace with visible state and approval.**

Milestone 1 is complete: PostgreSQL-backed IssueReport CRUD, API error contracts,
database integration tests, and a generated TypeScript client are in place.
RF-201 defined the reviewed extraction contract, RF-202 added the OpenAI and
fake provider boundary, and RF-203 added structured extraction with typed
failure reasons. RF-204 documented the tentative severity policy and examples,
and RF-205 added versioned prompts and per-call model settings records. RF-207
added bounded timeout and retry behavior, RF-208 added the reviewed offline
scenario suite, and RF-206 added the reviewed clarification policy. RF-209
verified the opt-in live check with schema shape, latency, and usage reporting.
RF-301 defined the reviewed workflow state: report references, saved extraction,
and typed drafts for later stages. RF-302 documented the reviewed normal,
clarification, rejection, failure, and resume paths. RF-303 implemented the
reviewed minimal typed graph; the full check passed, including all 127 tests
against local PostgreSQL (see `minimal-workflow.md`). RF-304 added the reviewed
bounded clarification branch with ordered answers and explicit incomplete
continuation; all 138 tests and quality checks passed. RF-305 added reviewed
PostgreSQL checkpoints and verified restoration in separate processes; all 146
tests and quality checks passed. RF-306 added reviewed immutable ticket proposals,
revision identities, risk details, and fingerprints; all 169 tests and quality
checks passed. RF-307 added the reviewed approval stage with exact proposal
binding and current support access checks; all 184 tests and quality checks
passed. RF-308 connected reviewed simulated execution with fresh support access
checks and deterministic checkpointed results; all 195 tests and quality checks
passed. RF-309 added reviewed guarded submissions, concurrent-process checks,
and sanitized failures; all 211 tests and quality checks passed. RF-310 saves
ordered, sanitized events with graph state; all 227 tests and quality checks
passed, and Kevin confirmed his final PAIR review on 2026-10-06. Phase 3 is
complete. RF-401 added eight reviewed sources for issue-report submission and
visibility, including fictional historical investigations and superseded advice.
Kevin completed the PAIR review; document links and whitespace checks passed.
RF-402 added reviewed typed document metadata and version-bound passage
locations. A typed LangGraph boundary replaced inline Pyright ignores; API
types, formatting, and lint passed, with 252 tests passing and 21 database tests
skipped. Kevin completed the PAIR review. RF-403 added reviewed manifest-driven Markdown
ingestion, source locations, hashes, and atomic in-memory revision storage. All
280 offline Python tests passed; 21 database tests were skipped. Types, lint,
formatting, and lockfile checks passed. Kevin completed the PAIR review.
RF-405 added reviewed PostgreSQL
knowledge revisions, chunks, 1536-dimensional vector storage, and async durable
ingestion. The local database was migrated with its named volume preserved;
all 311 tests and root quality checks passed. Kevin completed the PAIR review.
RF-406 compared fixed-size and heading-aware splitting on the eight sources.
Kevin approved one substantive section per chunk without overlap, preserving
metadata and source locations; documentation checks passed. The decision is
recorded in `chunking-strategy.md`.
RF-407's approved contract is implemented with typed requests/evidence, checked
adapter responses, and an offline fake. All 108 non-database knowledge tests,
strict API type checks, and knowledge lint/format checks pass. Kevin completed
the final PAIR review. RF-408's approved implementation prepares exact
heading chunks, validates bounded embedding inputs, persists vectors atomically,
and searches PostgreSQL with policy filters before ranking. LangChain is limited
to the embedding provider adapter. All 366 tests and root quality checks passed
against a disposable pgvector database. Kevin completed RF-408's final PAIR
review on 2026-10-08; no live embedding calls ran.
RF-409's approved contract is implemented with typed claim categories,
source-backed citation snapshots, eligibility/hash/excerpt/location checks,
and explicit supporting/contradicting references. Root quality checks and 366
offline tests passed, including 38 citation tests; 38 existing database tests
were skipped without `TEST_DATABASE_URL`. Kevin completed RF-409's final PAIR
review on 2026-10-08. The workflow diagnosis remains unchanged. The next ticket
is RF-410: measure retrieval relevance and exclusion behavior.
Kevin approved RF-410's six-case relevance specification and measurement rules.
The evaluator, fixture/live report format, and opt-in baseline command are
implemented. All 428 tests and root quality checks passed against a disposable
pgvector database. On 2026-10-09 Kevin completed the implementation review and
requested RF-410 be closed and work proceed. Its completion scope is the reviewed
evaluator, cases, and mechanical coverage; the live provider baseline is deferred.
No live embedding calls ran and provider relevance remains unmeasured. The next
ticket is RF-411: defend against document injection.
Kevin approved RF-411's defense rules and structural attack expectations. The
input/output boundary is implemented: verified evidence is serialized separately
from fixed instructions, generated output accepts only claim drafts, and source
references resolve through citation checks. Kevin completed the final PAIR review
on 2026-10-09; RF-411 is DONE. Root quality checks passed with 410 tests passing (including 22 new
boundary cases); 40 existing database tests skipped without `TEST_DATABASE_URL`.
Scope is deterministic application-boundary defenses; no diagnosis
model has been exercised and model-level injection resistance remains unmeasured.
The next ticket is RF-501: design the incident workspace information architecture.
The MVP Phase 4 tickets are complete within their recorded scopes; retrieval and
diagnosis generation are not yet connected to the workflow.
RF-404 PDF ingestion remains deferred beyond the MVP; the approved retrieval
corpus remains Markdown-only.

## Phase 0 — Scope and foundation

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-001 | Validate the MVP brief | PAIR | DONE | Rewrite or approve the user, MVP flow, non-goals, and three example journeys in `product.md` |
| RF-002 | Define domain terminology | PAIR | DONE | Review and approve `domain-language.md`: core terms have precise definitions, relationships, and visibility boundaries |
| RF-003 | Create monorepo skeleton | DELEGATE | DONE | Web/API directories, workspace, root commands, and documentation directory exist |
| RF-004 | Configure Python quality tools | PAIR | DONE | Ruff, type checker, pytest, and configuration checks run from the root |
| RF-005 | Configure frontend foundation | DELEGATE | DONE | React/TypeScript app builds and type-checks from the root |
| RF-006 | Create local PostgreSQL environment | PAIR | DONE | Compose database, readiness probe, environment example, and retained volume are documented |

## Phase 1 — Python and FastAPI foundation

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-101 | Model the issue-report domain in Python | HAND | DONE | Typed user/account references, report lifecycle, service, create, update, and response models validate correctly |
| RF-102 | Implement application factory and health API | HAND | DONE | Factory-based app exposes tested health/readiness behavior; existing global app is refactored as needed |
| RF-103 | Design the initial relational schema | HAND | DONE | Diagram documents issue-report ownership, keys, constraints, timestamps, and lifecycle status |
| RF-104 | Configure async SQLAlchemy sessions | PAIR | DONE | Engine, session lifecycle, transactions, and test override are implemented |
| RF-105 | Create initial Alembic migration | PAIR | DONE | Migration creates and cleanly rolls back the reviewed incident schema |
| RF-106 | Create and read issue reports | PAIR | DONE | POST, GET by ID, and list endpoints persist typed data within customer scope |
| RF-107 | Update and archive issue reports | PAIR | DONE | Partial update, missing record, ownership, and invalid transition behavior are tested |
| RF-108 | Define API error contracts | PAIR | DONE | Validation, not-found, conflict, and unexpected errors share a documented shape |
| RF-109 | Add database integration tests | PAIR | DONE | CRUD, validation, rollback/isolation, missing records, and transitions are covered |
| RF-110 | Generate TypeScript API client | DELEGATE | DONE | Repeatable generation produces a workspace package and drift can be detected |

## Phase 2 — Direct LLM integration

LangChain and LangGraph are intentionally excluded from this phase.

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-201 | Define extraction contract | PAIR | DONE | Schema includes summary, service, severity, confidence, facts, missing data, and questions |
| RF-202 | Build the LLM provider boundary | PAIR | DONE | OpenAI and deterministic fake providers satisfy one application-owned interface |
| RF-203 | Implement structured extraction | PAIR | DONE | Validated output handles malformed, missing, refusal, empty, and SDK-error cases |
| RF-204 | Define severity policy | PAIR | DONE | Written rules and examples prevent invented impact from raising severity |
| RF-205 | Version prompts and model settings | PAIR | DONE | Calls record prompt ID/version and model configuration |
| RF-206 | Implement clarification policy | PAIR | DONE | Explicit rules identify missing or contradictory context and limit questions |
| RF-207 | Add timeout and retry policy | PAIR | DONE | Transient and permanent failures are distinguished; retries are bounded |
| RF-208 | Add deterministic AI tests | PAIR | DONE | Default suite covers valid, ambiguous, malformed, timeout, refusal, and low-confidence cases offline |
| RF-209 | Add opt-in live model tests | PAIR | DONE | Separate command records shape, latency, and usage without exact-prose assertions |

## Phase 3 — Durable LangGraph workflow

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-301 | Design typed workflow state | PAIR | DONE | Durable and recomputable fields are identified for every workflow stage |
| RF-302 | Document transitions and failures | PAIR | DONE | Normal, clarification, rejection, provider failure, retrieval failure, and resume paths are drawn |
| RF-303 | Implement the minimal graph | PAIR | DONE | Classify, evaluate, diagnose, and report nodes execute with typed state |
| RF-304 | Add bounded clarification branch | PAIR | DONE | Workflow pauses/resumes, appends answers, limits loops, and permits incomplete continuation |
| RF-305 | Persist graph checkpoints | PAIR | DONE | A workflow resumes correctly after a process restart |
| RF-306 | Model proposed actions | PAIR | DONE | Action includes tool, arguments, explanation, effect, risk, version, and idempotency key |
| RF-307 | Implement approval interrupt | PAIR | DONE | Execution pauses and approval binds to exact immutable arguments |
| RF-308 | Implement simulated create-ticket tool | PAIR | DONE | Application code validates arguments and produces a deterministic fake result |
| RF-309 | Test approval edge cases | PAIR | DONE | Stale, changed, duplicate, rejected, concurrent, resumed, and failed executions are safe |
| RF-310 | Persist execution timeline | PAIR | DONE | Ordered, sanitized events explain all meaningful state transitions |

## Phase 4 — Retrieval and citations

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-401 | Author curated knowledge dataset | PAIR | DONE | Realistic runbooks include similar causes, stale advice, irrelevant text, and ambiguity |
| RF-402 | Define document metadata | PAIR | DONE | Source, title, type, service, version, date, access class, and location are typed |
| RF-403 | Ingest Markdown documents | PAIR | DONE | Parsing, hashing, idempotent re-ingestion, and errors are tested |
| RF-404 | Ingest PDF documents (post-MVP) | PAIR | PLANNED | Deferred beyond MVP by Kevin; future scope handles empty pages, bad extraction, tables, and page citations |
| RF-405 | Add pgvector schema and index | PAIR | DONE | Migration stores embeddings with documented index choice |
| RF-406 | Select chunking strategy | PAIR | DONE | Fixed and heading-aware approaches are compared and the decision is recorded |
| RF-407 | Implement retrieval boundary | PAIR | DONE | Framework-independent interface returns ranked typed evidence |
| RF-408 | Integrate selected LangChain pieces | PAIR | DONE | LangChain is limited to documented integration value, not domain contracts |
| RF-409 | Generate verifiable citations | PAIR | DONE | Claims distinguish support, inference, missing evidence, and conflict by stable location |
| RF-410 | Add retrieval tests | PAIR | DONE | Reviewed relevance cases/metrics and mechanical tests cover exclusion, filters, duplicates, empty results, and stale sources; live provider relevance baseline deferred at Kevin's request on 2026-10-09 |
| RF-411 | Defend against document injection | PAIR | DONE | Reviewed structural input/output defenses preserve application policy and tool approval boundaries; model-level resistance remains unmeasured |

## Phase 5 — Incident workspace

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-501 | Design workspace information architecture | PAIR | NEXT | Summary, state, questions, evidence, diagnosis, actions, approval, timeline, and metrics are placed |
| RF-502 | Implement incident CRUD screens | DELEGATE | PLANNED | Typed client and TanStack Query support create, list, view, and update states |
| RF-503 | Implement SSE transport | PAIR | PLANNED | Ordering, duplicate events, event IDs, reconnect, and terminal state are tested |
| RF-504 | Implement execution timeline | DELEGATE | PLANNED | UI renders persisted events rather than reconstructing them from chat |
| RF-505 | Implement clarification UI | DELEGATE | PLANNED | Current questions, previous answers, submit state, and resume are visible |
| RF-506 | Implement evidence panel | DELEGATE | PLANNED | Each citation exposes source, location, relevance, and supporting text |
| RF-507 | Design approval experience | PAIR | PLANNED | Exact action, arguments, reason, effect, risk, and reversibility are visible |
| RF-508 | Implement approve/reject controls | PAIR | PLANNED | Double submission, stale proposals, reconnects, and completed actions are safe |
| RF-509 | Display execution metrics | DELEGATE | PLANNED | Latency, model, tokens, cost estimate, and prompt version are shown |
| RF-510 | Add frontend tests | DELEGATE | PLANNED | Important loading, error, stream, evidence, clarification, and approval states are covered |

| RF-512 | Add authorized support report-state lookup | PAIR | PLANNED | Read-only lookup includes archived state within application-authorized account scope; permitted, denied, missing, and archived reads are tested; customer read behavior is unchanged; current state does not claim archive actor or time |

RF-512 requires Kevin's reviewed authorization contract before implementation
and must precede frontend demonstrations that verify a report is archived. It
builds on RF-106/107 and simulated identity; production authorization remains
RF-702. Archive history and restoration are outside this ticket.

## Phase 6 — Evaluations

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-601 | Define evaluation specification | HAND | PLANNED | Cases express expected service/severity, clarification, evidence, facts, and tool policy |
| RF-602 | Author 20 evaluation cases | HAND | PLANNED | Dataset has five straightforward, ambiguous, adversarial, and failure/safety cases each |
| RF-603 | Build evaluation runner | HAND | PLANNED | Versioned cases run repeatably and emit machine-readable results |
| RF-604 | Implement deterministic metrics | HAND | PLANNED | Classification, retrieval, citations, tools, and structure have code-based metrics |
| RF-605 | Add rubric-based judging | PAIR | PLANNED | Subjective rubric is explicit and judge model/version are retained |
| RF-606 | Generate evaluation report | DELEGATE | PLANNED | Human-readable scores, failures, regressions, and baseline comparison are produced |
| RF-607 | Run improvement experiment | HAND | PLANNED | At least one design change is compared with a baseline and interpreted |

## Phase 7 — Production quality

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-701 | Create threat model | HAND | PLANNED | Injection, leakage, access, secrets, approval, duplicates, and logs are analyzed |
| RF-702 | Add authentication and authorization | PAIR | PLANNED | Access policy and unauthorized paths are documented and tested |
| RF-703 | Enforce tool idempotency | HAND | PLANNED | Repeated or resumed runs cannot duplicate consequential actions |
| RF-704 | Add structured correlated logging | PAIR | PLANNED | Requests, runs, model calls, and tools are traceable without unsafe data |
| RF-705 | Record model cost and performance | PAIR | PLANNED | Model, prompt, tokens, latency, retries, and estimated cost persist per run |
| RF-706 | Add rate and input limits | DELEGATE | PLANNED | Limits and client-visible errors are tested |
| RF-707 | Harden container startup | DELEGATE | PLANNED | Images, migrations, health checks, and startup order are reproducible |
| RF-708 | Add continuous integration | DELEGATE | PLANNED | Lint, types, tests, integration smoke, eval smoke, and client drift checks run |
| RF-709 | Write architecture decisions | HAND | PLANNED | LangGraph, tool control, pgvector, approval, retrieval, and eval choices are defended |
| RF-710 | Deploy the demonstration | PAIR | PLANNED | Public demo uses safe simulated actions and documented configuration |

## Phase 8 — Portfolio package

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-801 | Write technical case study | HAND | PLANNED | Problem, constraints, architecture, risks, evaluation, results, and tradeoffs are explained |
| RF-802 | Polish architecture diagrams | PAIR | PLANNED | Diagrams accurately show system, workflow, and approval boundary |
| RF-803 | Record five-minute demo | HAND | PLANNED | Demo covers ambiguity, clarification, evidence, diagnosis, approval, timeline, and evals |
| RF-804 | Prepare interview explanations | HAND | PLANNED | Kevin can defend orchestration, validation, approval, retrieval, evaluation, resume, and idempotency |
| RF-805 | Polish repository and resume story | PAIR | PLANNED | All claims are concise, measurable, and supported by the implementation |

## Milestone sequence

1. Tested Incident CRUD backed by PostgreSQL
2. Validated structured AI extraction with deterministic tests
3. Durable workflow with clarification and resume
4. Small retrieval slice with verifiable citations
5. Inspectable incident workspace
6. Safe approval and simulated execution
7. Evaluation baseline and measured improvement
8. Hardened, deployed portfolio demonstration
