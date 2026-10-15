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

RF-505 is DONE: customer clarification controls passed automated checks and
real browser/API/PostgreSQL verification on 2026-10-12. Kevin approved RF-507's
approval experience on the same date; it is DONE. Kevin accepted RF-512's final
PAIR review on 2026-10-13; it is DONE. RF-506 is DONE within the approved separate
preliminary support-analysis scope, with saved verified evidence and production
browser checks. RF-508's approved support simulation API and controls are
implemented and verified; Kevin accepted final PAIR review on 2026-10-13, so
RF-508 is DONE. RF-509 is DONE within the approved latest-extraction display
scope. RF-510 is DONE: the frontend coverage audit added 15 regression cases;
all 184 frontend tests, TypeScript checks, and the production build passed.
RF-601 is NEXT under PAIR ownership. Full metrics accounting
remains RF-705. The broader hands-on platform checkpoint remains pending;
see `customer-intake-runs.md`.

Phases 1–3 are complete. MVP Phase 4 is complete within its recorded scopes:
retrieval and diagnosis are not connected to the workflow, provider retrieval
relevance and diagnosis-model injection resistance remain unmeasured, and PDF
ingestion (RF-404) is deferred beyond the MVP. The corpus is Markdown-only.
RF-502's implementation is verified; hands-on UI review is deferred to the
platform checkpoint and its status remains READY.

The records below preserve ticket verification history. Counts describe each
run, not the current test-suite size. Detailed contracts live in the ticket docs.

| Ticket | Delivered and reviewed | Verification and limits |
| --- | --- | --- |
| Phase 1 | PostgreSQL IssueReport CRUD, API errors, database integration tests, generated TypeScript client | Complete |
| RF-201–205 | Extraction contract, OpenAI/fake boundary, structured extraction with typed failures, tentative severity policy/examples, versioned prompts and per-call settings | Reviewed |
| RF-206–209 | Clarification policy, bounded timeout/retries, offline scenarios, opt-in live schema/latency/usage check | Reviewed; live check verified |
| RF-301–302 | Typed state with report references, extraction and future drafts; normal, clarification, rejection, failure, and resume paths | Reviewed |
| RF-303 | Minimal typed graph (`minimal-workflow.md`) | Full check; 127 tests with local PostgreSQL |
| RF-304 | Bounded clarification, ordered answers, explicit incomplete continuation | Quality checks; 138 tests |
| RF-305 | PostgreSQL checkpoints and separate-process restoration | Quality checks; 146 tests |
| RF-306 | Immutable proposals, revision identities, risk, fingerprints | Quality checks; 169 tests |
| RF-307 | Approval bound to exact proposal with current support access checks | Quality checks; 184 tests |
| RF-308 | Simulated execution with fresh access checks and checkpointed deterministic results | Quality checks; 195 tests |
| RF-309 | Guarded submissions, concurrent-process checks, sanitized failures | Quality checks; 211 tests |
| RF-310 | Ordered sanitized events saved with graph state | Quality checks; 227 tests. Kevin confirmed final PAIR review on 2026-10-06 |
| RF-401 | Eight submission/visibility sources, including fictional investigations and superseded advice | PAIR review, document links, whitespace passed |
| RF-402 | Typed metadata and version-bound locations; typed LangGraph boundary replaces inline Pyright ignores | PAIR review; API types, formatting, lint passed; 252 tests passed, 21 database tests skipped |
| RF-403 | Manifest-driven Markdown ingestion, locations, hashes, atomic memory revision store | PAIR review; types, lint, formatting, lockfile passed; 280 offline tests passed, 21 database tests skipped |
| RF-405 | PostgreSQL revisions, chunks, 1536-dimensional vectors, async ingestion | PAIR review; root checks and all 311 tests passed. Local database migrated with named volume preserved |
| RF-406 | Compared fixed-size and heading splitting on eight sources; selected one substantive section per chunk, no overlap, preserved metadata/locations (`chunking-strategy.md`) | PAIR review; documentation checks passed |
| RF-407 | Typed requests/evidence, checked adapters, offline fake | Final PAIR review; 108 non-database knowledge tests, strict API types, knowledge lint/format passed |
| RF-408 | Exact heading chunks, bounded embedding inputs, atomic vectors, PostgreSQL filtering before ranking; LangChain limited to embedding adapter | Final PAIR review on 2026-10-08; root checks and all 366 tests passed on disposable pgvector. No live embeddings |
| RF-409 | Claim categories, citation snapshots, eligibility/hash/excerpt/location checks, supporting/contradicting references | Final PAIR review on 2026-10-08; root checks and 366 offline tests including 38 citation tests passed; 38 database tests skipped without `TEST_DATABASE_URL`. Workflow diagnosis unchanged |
| RF-410 | Six approved relevance cases/metrics, evaluator, fixture/live report format, opt-in baseline command | Kevin closed after implementation review on 2026-10-09. Root checks and all 428 tests passed on disposable pgvector. Completion covers evaluator/cases/mechanics; live baseline deferred, no live embeddings, provider relevance unmeasured |
| RF-411 | Approved structural defenses/attacks: verified evidence separate from instructions, claim-only output, references resolved through citation checks | Final PAIR review on 2026-10-09; root checks and 410 tests including 22 new boundary cases passed; 40 database tests skipped without `TEST_DATABASE_URL`. No diagnosis-model evaluation; model injection resistance unmeasured |
| RF-501 | Navigation, wireframe, nine areas, loading/failure/decision states, integration order (`workspace-information-architecture.md`) | Kevin approved layout/behavior/sequence on 2026-10-09; document links/whitespace passed. Customer CRUD available; support/workflow integration separately scoped |
| RF-502 | Typed client/Query list, create, detail, service edit, archive; in-memory demo sessions and interaction tests. Immutable description; list preview because API has no title. Tailwind Vite styling with shared utilities/local JSX | Root checks; 410 backend and 11 frontend tests passed, 40 database tests skipped without `TEST_DATABASE_URL`. Chromium desktop/mobile CRUD/hydration passed with HTTP mocks. Hands-on review pending at platform checkpoint; READY. Kevin requested RF-503 next. See `customer-report-screens.md` |
| RF-503 | Approved customer-only read transport, SSE framing, snapshot validation, access rechecks, heartbeat/rollover, browser parsing, bounded reconnects | Contract/split approved on 2026-10-09; Kevin accepted by requesting next ticket. `pnpm check`: 434 backend and 47 frontend tests passed, 40 database tests skipped without `TEST_DATABASE_URL`. Deterministic authorized sources; DONE within transport scope |
| RF-511 | Durable one-run-per-report registry; account-scoped start/read/clarification/recovery; pause/operation guards; integrated customer SSE. Default labeled offline simulation. Generated run/snapshot types used by browser validator | Kevin approved sequence before RF-504, lifecycle/access/execution/recovery contract, and implementation; DONE. `pnpm check`: all 504 backend and 47 frontend tests passed on disposable pgvector, including migration/concurrency/restart. No live model calls or project database changes |
| RF-513 | Authorized support run/timeline reads required by RF-504 | Final PAIR review accepted on 2026-10-12; full checks passed with 517 backend and 47 frontend tests on disposable PostgreSQL, followed by all 14 expanded support-read tests; see `support-run-reads.md` |
| RF-504 | Separate support entry and saved intake timeline; Zod response validation, refresh/stale/access-loss states, identity/report isolation, and explicit outcome labels | DONE on 2026-10-12. Root checks: all 518 backend and 85 frontend tests passed on disposable pgvector, no skips. Production Chromium used real HTTP/persisted checkpoints: refresh, clarification, reload/restart, outage, archival, revoked grants, account/session isolation, and desktop/mobile passed; see `execution-timeline-ui.md` |
| RF-512 | Authorized current report-state lookup, including archived reports without an intake run; explicit support account grants and access rechecks | Final PAIR review accepted on 2026-10-13. Recorded root checks: 540 backend and 103 frontend tests passed on disposable PostgreSQL, no skips; see `support-report-state.md`. Reviewed frontend cleanup separates intake streaming from action coordination; all 103 frontend tests, TypeScript checks, and production build passed |
| RF-506 | Explicit preliminary support analysis, durable UUID-bound results, current report/source access checks, verified citations, and an evidence panel | Kevin approved the separate support integration on 2026-10-13. Root checks: 563 backend and 120 frontend tests passed, no skips, on disposable PostgreSQL 16 / pgvector 0.6.0; migration roundtrip and ORM drift passed. Production Chromium verified real HTTP, saved results, API restart, desktop/mobile, input freshness, archival, and access loss. Default labeled simulation; no live calls. See `evidence-panel.md` |
| RF-509 | Authorized latest-extraction metrics projection and support panel; missing latency/cost explicit, scoped contract approved | Root checks: 601 backend and 169 frontend tests, no skips, on disposable PostgreSQL. Production Chromium real HTTP/checkpoint reads, reload, offline recovery, desktop/mobile, empty/archived and foreign-account cases passed on 2026-10-13; full accounting remains RF-705. See `execution-metrics-ui.md` |
| RF-510 | Frontend coverage audit and 15 regression cases; real combined support panels and clarification reconciliation | All 184 frontend tests, TypeScript checks, and production build passed on 2026-10-13. No runtime changes; controlled HTTP tests do not complete the hands-on platform checkpoint. See `frontend-tests.md` |

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

### Platform review checkpoints

Kevin requested reviewing UI and integration as working flows rather than
reviewing each screen separately. Keep automated verification per ticket;
batch his hands-on platform review at these checkpoints. PAIR decisions about
authorization, approval, and workflow behavior still require his review before
implementation.

- **Customer report flow (available for an early check after RF-502):** create,
  list, open, edit/clear service, and archive through the running API and database;
  check reload persistence, validation, and two customer identities. RF-502's
  browser verification so far used mocked HTTP responses. Kevin's hands-on review
  is deferred to the integrated review unless he chooses this earlier checkpoint.
- **Main platform checkpoint (after RF-510 and required backend integration):**
  test customer intake and clarification, then support diagnosis with citations,
  exact-action approve/reject, simulated execution, persisted timeline, and
  available metrics. Include reload/reconnect, stale approval, failures, and
  account isolation. Use actual application endpoints and persisted state;
  deterministic backend model adapters may keep this offline, with simulation
  clearly labeled. Frontend HTTP mocks alone do not satisfy this checkpoint.

The main checkpoint depends on the missing support-read and workflow HTTP,
confirmation, retrieval/diagnosis, and proposal integrations recorded in
`workspace-information-architecture.md`. RF-512 must also precede verified
archival demonstrations. Scope those integrations explicitly before dependent
UI tickets; completing RF-510 alone does not make the platform ready. Record
Kevin's walkthrough results and fixes before closing the platform review.

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-501 | Design workspace information architecture | PAIR | DONE | Summary, state, questions, evidence, diagnosis, actions, approval, timeline, and metrics are placed |
| RF-502 | Implement incident CRUD screens | DELEGATE | READY | Implementation and automated checks verified; Kevin's hands-on review deferred to platform checkpoint; typed client and TanStack Query support create, list, view, and update states |
| RF-503 | Implement SSE transport | PAIR | DONE | Approved transport/lifecycle split; ordering, duplicate events, IDs, reconnect, access loss, and terminal state are implemented and tested; Kevin accepted the scoped implementation |
| RF-504 | Implement execution timeline | DELEGATE | DONE | Automated checks and real browser/API/PostgreSQL integration verified on 2026-10-12. Authorized internal UI renders persisted events rather than reconstructing them from chat; preserves saved ordering/timestamps and distinguishes loading, empty, error, stale, and access-loss states; see execution-timeline-ui.md; dependencies RF-310, RF-511, and RF-513 are DONE |
| RF-505 | Implement clarification UI | DELEGATE | DONE | Current questions, accepted previous answers, submit state, and explicit recovery are visible; 518 backend and 103 frontend tests passed with no skips, plus real browser/API/PostgreSQL verification on 2026-10-12; see customer-clarification-ui.md |
| RF-506 | Implement evidence panel | DELEGATE | DONE | Each citation exposes source, location, relevance, and supporting text through the approved separate preliminary support-analysis integration; durable operations and current report/source access checks verified; 563 backend and 120 frontend tests plus real browser/API/PostgreSQL checks passed on 2026-10-13; see evidence-panel.md |
| RF-507 | Design approval experience | PAIR | DONE | Kevin approved the complete action card, inline approve/reject confirmations, reversibility treatment, and separate decision/execution outcomes on 2026-10-12; see approval-experience.md |
| RF-508 | Implement approve/reject controls | PAIR | DONE | Approved manual support simulation API and controls are implemented; duplicate/stale decisions, reconnects, changed input, access loss, and completed/interrupted outcomes verified. Root checks: 585 backend and 152 frontend tests, no skips; real browser/API/PostgreSQL restart passed on 2026-10-13. Kevin accepted final PAIR review on 2026-10-13; see support-approval-controls.md |
| RF-509 | Display execution metrics | DELEGATE | DONE | Kevin approved the latest saved intake extraction scope on 2026-10-13: configured model, prompt version, attempts, and returned usage displayed; latency/cost explicitly not recorded, full accounting remains RF-705. Root checks: 601 backend and 169 frontend tests, no skips; real HTTP/PostgreSQL production browser checks passed. See execution-metrics-ui.md |
| RF-510 | Add frontend tests | DELEGATE | DONE | Coverage map and 15 regression cases added for combined support access loss/late results and clarification reconciliation. All 184 frontend tests, TypeScript checks, and production build passed on 2026-10-13; see frontend-tests.md. Hands-on platform checkpoint remains pending |
| RF-511 | Expose customer intake run lifecycle | PAIR | DONE | Approved prerequisite to RF-504: reviewed durable run/report binding, authorized start/read/clarification resume, safe snapshot revisions, and RF-503 route integration; implementation approved by Kevin; all 504 backend and 47 frontend tests passed; see customer-intake-runs.md |

| RF-512 | Add authorized support report-state lookup | PAIR | DONE | Read-only lookup includes archived state within application-authorized account scope; permitted, denied, missing, and archived reads are tested; customer read behavior is unchanged; current state does not claim archive actor or time; Kevin accepted final PAIR review on 2026-10-13 |
| RF-513 | Expose authorized support run/timeline reads | PAIR | DONE | Kevin approved per-support-user account grants, archived timeline reads, and the closed intake response; implementation and automated checks verified; final PAIR review accepted on 2026-10-12; see support-run-reads.md |

RF-513 records the existing internal-read prerequisite in
`execution-timeline-ui.md`. It builds on RF-310, RF-511, and simulated identity,
and must precede RF-504's live integration. Kevin approved its authorization
and response contract on 2026-10-09. The read-only endpoint, current account
checks, saved-event validation, generated client, configuration, and tests are
implemented. Full `pnpm check` passed with 517 backend and 47 frontend tests
against disposable PostgreSQL; the final expanded focused suite passed all 14
support-read tests. No live provider calls ran or project database changes were
made. RF-512 remains a separate
current-report-state lookup; neither endpoint implicitly grants the other's
access. Kevin accepted the final PAIR implementation review on 2026-10-12.
RF-513, RF-504, RF-505, RF-506, RF-507, RF-508, RF-509, RF-510, and RF-512 are
DONE; RF-601 is NEXT. The
[approved approval experience](approval-experience.md) builds on RF-306/307 and
RF-501 placement. Kevin accepted its complete read-only action card, inline
confirmations for both decisions, simulation/reversibility copy, and separate
decision/execution outcomes on 2026-10-12. Documentation checks passed.
Approval controls (RF-508) now have the separately approved support simulation
HTTP integration; Kevin accepted final PAIR review on 2026-10-13. RF-512 uses
existing report persistence and simulated support grants,
independently of that integration.

Kevin approved RF-512's [endpoint and access contract](support-report-state.md)
on 2026-10-12. The separate state-only endpoint is implemented, including
archived reads without an intake run, shared explicit support grant checks,
and generated client types. `pnpm check` passed 540 backend and 103 frontend
tests with no skips against disposable PostgreSQL, plus formatting, lint,
type/build, and generated-client checks. Kevin accepted final PAIR implementation
review on 2026-10-13; RF-512 is DONE. The reviewed frontend cleanup extracted
intake stream lifecycle handling and clarified asynchronous guards; all 103
frontend tests, TypeScript checks, and the production build passed afterward.

RF-512's authorization contract is approved. Its endpoint must precede frontend
demonstrations that verify a report is archived. It builds on RF-106/107 and simulated identity; production authorization remains
RF-702. Archive history and restoration are outside this ticket.

Kevin approved RF-506's [separate preliminary support analysis](evidence-panel.md)
and extended account-grant policy on 2026-10-13. It builds on RF-407/408 retrieval,
RF-409 citations, RF-411 analysis, and RF-501 placement. Explicit operations now
save verified results and the support panel exposes their provenance. Customer
confirmation and automatic workflow diagnosis remain separate work. Live provider
relevance and model injection resistance remain unmeasured; interrupted analysis
recovery needs a separate reviewed contract. RF-506 is DONE within this scope.

RF-508 is DONE under PAIR ownership after Kevin accepted the implementation
review on 2026-10-13. Its reviewed behavior binds a human decision to the exact
saved action across stale, repeated, interrupted, and completed operations.

Kevin approved the [RF-508 HTTP integration contract](support-approval-controls.md)
and mutation access on 2026-10-13: manually authored simulation proposals after
intake, with unconfirmed observations labeled explicitly, and support account
grants extended to preparation, decision, and simulated execution. Root checks
passed 585 backend and 152 frontend tests with no skips; migration roundtrip and
ORM drift passed on disposable PostgreSQL. Production Chromium verified the card,
two reviewers, stale replies, archival/access loss, and process restart with no
execution retry. Customer summary confirmation and automatic proposal generation
remain separate work. Kevin accepted final PAIR implementation review on 2026-10-13.

RF-509 is DONE under DELEGATE ownership within Kevin's approved 2026-10-13
[latest-extraction display scope](execution-metrics-ui.md). The read-only support
endpoint uses existing account grants and fresh access/report/run checks. It
projects the latest checkpointed extraction record without invoking a provider,
graph, or tool. Missing latency and cost are explicitly not recorded; usage is
for the final returned response, not a total over retries or clarification rounds.
Full per-call history and numeric duration/cost accounting remain RF-705.
Root formatting/lint, generated-client drift, Python/TypeScript types, production
build, and all 601 backend and 169 frontend tests passed with no skips on
disposable PostgreSQL. Production Chromium verified real HTTP/checkpoint reads,
reload, offline stale/recovery behavior, desktop/mobile, empty/archived reports,
and foreign-account access loss. No live provider calls or project database
changes were made.

RF-510 is DONE under DELEGATE ownership. The [frontend coverage map](frontend-tests.md)
records all eight suites and their limits. Eleven new cases mount every real
support panel together to cover independent loading/failure, shared access loss,
late mutation responses, and cancellation. Four clarification cases cover a
terminal stream update awaiting a full read, draft retention during temporary
read failure, a previously visible run returning 404, and invalid streamed state.
All 184 frontend tests, TypeScript checks, and the production build passed on
2026-10-13. No application behavior or backend contract changed. The hands-on
platform checkpoint and remaining integrations are still pending.

RF-601 is NEXT under PAIR ownership. Kevin owns evaluation expectations and
acceptance criteria; Codex may help draft and implement the agreed specification
for service/severity, clarification, evidence, facts, and tool policy. It builds on the reviewed extraction, retrieval/citation, workflow,
and approval contracts. Existing RF-410 relevance cases can inform it but do
not complete it. First distinguish behavior that can be measured now from
planned integration and live-provider quality that remains unmeasured. Codex
may suggest approaches and implement agreed parts; Kevin reviews the cases,
expected behavior, and metric interpretation.

## Phase 6 — Evaluations

Kevin changed RF-601–604 and RF-607 from HAND to PAIR on 2026-10-13.
He retains decisions about evaluation expectations and metric interpretation
under the [PAIR agreement](working-agreement.md#pair).

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-601 | Define evaluation specification | PAIR | NEXT | Cases express expected service/severity, clarification, evidence, facts, and tool policy |
| RF-602 | Author 20 evaluation cases | PAIR | PLANNED | Dataset has five straightforward, ambiguous, adversarial, and failure/safety cases each |
| RF-603 | Build evaluation runner | PAIR | PLANNED | Versioned cases run repeatably and emit machine-readable results |
| RF-604 | Implement deterministic metrics | PAIR | PLANNED | Classification, retrieval, citations, tools, and structure have code-based metrics |
| RF-605 | Add rubric-based judging | PAIR | PLANNED | Subjective rubric is explicit and judge model/version are retained |
| RF-606 | Generate evaluation report | DELEGATE | PLANNED | Human-readable scores, failures, regressions, and baseline comparison are produced |
| RF-607 | Run improvement experiment | PAIR | PLANNED | At least one design change is compared with a baseline and interpreted |

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
