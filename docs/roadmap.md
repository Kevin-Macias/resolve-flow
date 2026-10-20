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

Kevin approved recipient-chosen invitation emails on 2026-10-20. Follow-up
implementation and verification are recorded in `authentication-and-access.md`;
RF-710 remains NEXT.

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
RF-601 is DONE after Kevin approved the evaluation specification on 2026-10-14.
RF-602 is DONE: Kevin approved all 20 case labels on 2026-10-14.
RF-603 is DONE after Kevin accepted final PAIR review on 2026-10-15.
RF-604 is DONE after Kevin accepted final PAIR review on 2026-10-15.
RF-605 is DONE after Kevin accepted final PAIR review on 2026-10-15.
RF-606 is DONE after DELEGATE implementation and verification on 2026-10-15.
RF-607 is DONE after Kevin accepted the comparison and decision to keep v3
on 2026-10-15. RF-701–703 are DONE after Kevin accepted final reviews on 2026-10-18.
RF-704 and RF-705 are DONE after final PAIR review on 2026-10-18. RF-706 is
DONE after DELEGATE implementation and verification. RF-707 is also DONE after
verified container startup work. RF-708 is DONE for its locally verified CI
implementation; its first hosted run awaits a push. RF-709 is DONE; RF-710 is NEXT.
Kevin approved RF-703's separate durable simulation design on 2026-10-15;
its implementation passed final PAIR review on 2026-10-18.
The broader hands-on platform checkpoint remains pending;
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
| RF-601 | Approved evaluation specification for separate implemented targets, reviewed expectations, fixture/live modes, and explicit assessment limits | Kevin accepted PAIR review on 2026-10-14. Documentation links, whitespace, and single NEXT ticket passed; no evaluator code, live calls, or case labels. See `evaluation-specification.md` |
| RF-602 | Approved 20-case set, exact inputs/fixtures, expectations, target applicability, and provenance; workspace-evaluation-v1 frozen | Kevin accepted PAIR review on 2026-10-14. Offline counts/schema/reference/policy consistency and documentation checks passed. No scenario execution or live calls; see `evaluation-cases.md` |
| RF-603 | Repeatable fixture runner for all 20 cases with isolated approval state, JSON observations/provenance, and explicit unmeasured quality | Kevin accepted final PAIR review on 2026-10-15. Root checks: 625 backend and 184 frontend tests, no skips; 24 focused tests and full fixture runs passed. No live calls or project database changes; see `evaluation-runner.md` |
| RF-604 | Offline deterministic scorer for classification, clarification, retrieval/citations, exact saved approval bindings, and structure | Kevin accepted final PAIR review on 2026-10-15. Root checks: 659 backend and 184 frontend tests, no skips; 123 fixture checks passed, zero failures/errors, six semantic assessments unmeasured. See `deterministic-metrics.md` |
| RF-605 | Approved extraction rubric and separate judging command with explicit model/version, prompt/rubric provenance, and status accounting | Kevin accepted final PAIR review on 2026-10-15. Root checks: 698 backend and 184 frontend tests, no skips; 37 judge tests and two provider provenance tests. No live judge calls or human calibration; see `rubric-judging.md` |
| RF-606 | Readable evaluation report with validated artifact bundles, explicit assessment limits, and compatible baseline comparisons | DELEGATE implementation verified on 2026-10-15. Root checks: 732 backend and 184 frontend tests, no skips; 34 reporting tests passed separately. Generated fixture report and comparison control; no live calls or improvement claim. See `evaluation-report.md` |
| RF-607 | Controlled live prompt comparison and reviewed decision to retain v3 | Kevin accepted final PAIR interpretation on 2026-10-15. Twelve successful calls: baseline 23/33 deterministic passes, candidate 22/33; A01 question-count regression rejected the candidate. Prior full checks: 765 backend/184 frontend, no skips; subsequent report fix: 34 focused tests, lint/types passed. Semantic judgments remain unmeasured; see `improvement-experiment.md` |

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
DONE; RF-601–607 and RF-701–708 are also DONE, and RF-709 is DONE; RF-710 is NEXT. The
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

RF-601 is DONE under PAIR ownership. Kevin approved the
[evaluation specification](evaluation-specification.md) on 2026-10-14: separate
implemented targets and fixture/live results, reviewed case expectations,
deterministic versus semantic assessment, explicit incomplete results, and the
case/result contract for RF-602–604. Documentation links and whitespace passed;
no evaluator code, case labels, thresholds, or live runs were introduced.

RF-602 is DONE under PAIR ownership. Kevin approved the
[20 cases](evaluation-cases.md) and their expected outcomes on 2026-10-14,
freezing `workspace-evaluation-v1`: five straightforward, five ambiguous, five
adversarial, and five failure/safety cases. Group counts, unique IDs, source and
policy references, extraction fixtures, proposal fields, and fixture-policy
consistency passed offline checks. Approval changed version/review metadata only;
no labels changed after review. These checks validate the dataset, not actual
scenario execution or model quality.

RF-603 is DONE under PAIR ownership after Kevin accepted final implementation
review on 2026-10-15. Its contract is to run the approved
versioned cases repeatably and emit machine-readable results. It depends on
RF-601's specification, RF-602's frozen case set, and existing application
boundaries. Keep observed results separate from expected labels; distinguish
handled application failures from evaluator errors and unmeasured semantic
quality. The immediate learning objective is to build a repeatable harness that
exercises actual code without treating fixture success as provider quality.
Live runs remain separately authorized; RF-604 owns deterministic metrics. The
[fixture runner](evaluation-runner.md) is implemented and has executed all 20
cases without executor errors. Kevin accepted final PAIR implementation review
on 2026-10-15; completion does not imply matching labels or measured model quality. Root
checks passed formatting/lint, generated-client drift, Python/TypeScript checks,
the production build, all 625 backend tests, and all 184 frontend tests with no
skips on disposable PostgreSQL/pgvector on 2026-10-15. The 24 focused runner tests
passed separately. The project database and approved case labels are unchanged.

RF-604 is DONE after Kevin accepted final PAIR review on 2026-10-15. It depends on RF-601's approved measurement
semantics, RF-602's frozen labels, RF-603's observed results, and RF-410's
retrieval metric definitions. Its goal is code-based checks for classification,
retrieval, citations, tools, and structure, with explicit applicability and
pass/fail/error/unmeasured counts. The immediate learning objective is to compare
observations with reviewed expectations without hiding errors in averages or
claiming semantic quality from structural checks. Subjective judging remains
RF-605; new thresholds or interpretations require Kevin's review. The offline
[scorer](deterministic-metrics.md) now checks classification, clarification,
retrieval/citations, saved approval bindings, and structure. Summaries retain
separate named metrics, explicit denominators, and missing/error slots. The
fresh fixture baseline has 123 passing checks, zero failures/errors, and six
unmeasured semantic assessments. Root checks passed on 2026-10-15: 659 backend
and 184 frontend tests with no skips, lint, type checks, generated-client drift,
and the production build. Kevin accepted the final PAIR review on 2026-10-15.

RF-605 is DONE after Kevin accepted final PAIR review on 2026-10-15. Its goal is explicit subjective rubrics
with retained judge model/version, building on RF-601's measurement limits,
RF-602's frozen semantic review notes, and RF-603/604's observation and scoring
artifacts. The learning objective is to assess meaning with reviewable criteria
while keeping judge opinions separate from deterministic checks and fixture
mechanics. Kevin approved the scope, criteria, and status rules on 2026-10-15.
The [judging command](rubric-judging.md) is implemented with offline tests and
explicit model/prompt/rubric provenance. Root checks passed on 2026-10-15:
698 backend and 184 frontend tests with no skips, lint, types, generated-client
drift, and production build. Kevin accepted final PAIR implementation review on
2026-10-15.
No live judge run or calibration labels have been approved.

RF-606 is DONE under DELEGATE ownership after implementation and verification
on 2026-10-15. It depends on RF-603's observations,
RF-604's deterministic scores, and RF-605's separate semantic assessments.
Its goal is a human-readable report of scores, failures, regressions, and a
baseline comparison. The learning objective is to interpret compatible artifacts
with visible denominators, provenance changes, and unmeasured quality. A report
must preserve the fixture/live and deterministic/judge distinctions; an absent
baseline cannot be presented as evidence of improvement. The
[report command](evaluation-report.md) validates matching artifacts and renders
Markdown with explicit errors, unmeasured checks, and compatible comparisons.
Root checks passed: 732 backend and 184 frontend tests, no skips, lint, types,
generated-client drift, and production build. All 34 focused reporting tests
passed separately. The generated same-artifact comparison is a control; no
improvement experiment or live baseline was run.

RF-607 is DONE after Kevin accepted the comparison interpretation and rejected
the candidate on 2026-10-15. It depends on the reviewed cases,
repeatable observations/scoring/judging, and RF-606's report/comparison command.
Kevin owns the design change, baseline, success criteria, and interpretation.
The learning objective is to compare a concrete change on compatible inputs
and explain the measured result and its limits without treating fixture
mechanics as evidence of live model quality. The
[prompt experiment](improvement-experiment.md) records Kevin's approved prompt
addition, six-case live extraction comparison (12 calls, no retries), and
human-reviewed decision rule. The configured model is gpt-6-luna with low
reasoning effort. After an initial authentication-failed run, Kevin corrected the
key and explicitly approved a fresh 12-attempt run. All fresh calls completed
without provider errors: baseline 23/33 deterministic passes, candidate 22/33.
A01 question_count regressed from pass to fail, so the approved rule does not
support adopting the candidate. The app remains on v3 and semantic judgments
remain unmeasured. Kevin accepted the deterministic rejection and interpretation
on 2026-10-15; both run artifacts are preserved.
Implementation checks passed on 2026-10-15: 765 backend and 184 frontend tests
with no skips, lint, types, generated-client checks, and production build. The
existing restart test failed once, then passed isolated and in the full rerun;
see the experiment record.

## Phase 6 — Evaluations

Kevin changed RF-601–604 and RF-607 from HAND to PAIR on 2026-10-13.
He retains decisions about evaluation expectations and metric interpretation
under the [PAIR agreement](working-agreement.md#pair).

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-601 | Define evaluation specification | PAIR | DONE | Kevin approved the target/mode, case expectations, measurement, result, and reporting contract on 2026-10-14; covers service/severity, clarification, evidence, facts, and tool policy. Documentation links and whitespace passed; see evaluation-specification.md |
| RF-602 | Author 20 evaluation cases | PAIR | DONE | Kevin approved all 20 scenarios and labels on 2026-10-14; workspace-evaluation-v1 has five cases per group. Offline schemas, references, and fixture-policy consistency verified; scenarios not yet executed. See evaluation-cases.md |
| RF-603 | Build evaluation runner | PAIR | DONE | Fixture runner implemented: all 20 approved cases execute with separate observations/labels and machine-readable provenance; isolated PostgreSQL approval, cancellation cleanup, safe errors, and output-file protection verified. Root checks: 625 backend and 184 frontend tests, no skips, on 2026-10-15. Kevin accepted final PAIR review on the same date; see evaluation-runner.md |
| RF-604 | Implement deterministic metrics | PAIR | DONE | Code-based classification, retrieval/citation, tool-binding, and structure checks implemented; explicit per-metric status counts and denominators. Root checks: 659 backend and 184 frontend tests, no skips, on 2026-10-15. Kevin accepted final PAIR review on 2026-10-15; see deterministic-metrics.md |
| RF-605 | Add rubric-based judging | PAIR | DONE | Kevin approved the extraction rubric on 2026-10-15; separate judging command retains model/settings, resolved version when returned, prompt/rubric hashes, and explicit statuses. Root checks: 698 backend and 184 frontend tests, no skips. Kevin accepted final PAIR review on 2026-10-15; no live judging/calibration. See rubric-judging.md |
| RF-606 | Generate evaluation report | DELEGATE | DONE | Offline Markdown reports bind matching observations/scores/judgments; show separate metrics, failures, provenance, status changes, and guarded baseline comparisons. Root checks: 732 backend and 184 frontend tests, no skips, on 2026-10-15; 34 reporting tests passed. See evaluation-report.md |
| RF-607 | Run improvement experiment | PAIR | DONE | Approved live prompt comparison executed after key correction: 12 successful calls, baseline 23/33 deterministic passes vs candidate 22/33. A01 question-count regression prevents adoption under the agreed rule; v3 retained. Checks: 765 backend and 184 frontend tests, no skips. Kevin accepted the interpretation and rejection on 2026-10-15; semantic judgments remain unmeasured. The later report-order fix passed 34 focused tests, lint, and types; see improvement-experiment.md |

RF-701 is DONE after Kevin accepted the threat-model review on 2026-10-18.
The [threat model](threat-model.md) maps assets, trust boundaries, and eight
threat scenarios to implementation/test evidence and follow-up priorities.
It covers injection, leakage, access, secrets, approval, duplicate effects, and
logs. Accepting the analysis does not claim production readiness or close the
remaining operational and provider-data handling gaps.
Verification on 2026-10-15: all 43 draft links resolve, documentation whitespace
checks pass, and 87 focused offline regression tests pass. The sandboxed approval
test stalled; the same focused suite passed outside the sandbox in 1.14 seconds.
No database-backed tests or live providers were run for this documentation task.

RF-703's [durable simulation](tool-idempotency.md) is implemented under Kevin's
approved PAIR contract: commit application intent before dispatch, commit the
simulated destination effect/receipt together, and explicitly recover with the
same proposal/key after a crash. The recovery API preserves current support
access, observation freshness, and exact approval checks. Unknown legacy attempts
without durable intent remain manual; GETs and duplicate decisions never recover
execution. The generated client includes the command; support UI controls remain
unchanged. This is a local simulation demonstration, not a real external-effect
guarantee. Kevin accepted final PAIR implementation review on 2026-10-18;
RF-703 is DONE within the approved local simulation scope.
Verification on 2026-10-15: `pnpm check` passed formatting/lint, generated-client
drift, Python/TypeScript checks, production build, all 781 backend tests, and all
184 frontend tests with no skips. All 15 focused recovery tests passed separately.
Tests terminate real processes at four execution boundaries and recover in a
fresh interpreter; a deterministic pending-node-write regression preserves the
saved approval and contiguous event history. Migration `0006` upgrade/rollback
and ORM drift passed in a separate disposable database. The project database was
not migrated; no live provider or external tool was called.

## Phase 7 — Production quality

RF-702's [invitation authentication](authentication-and-access.md) is implemented
under PAIR ownership. Kevin selected permanent onboarding and email/password
repeat login on 2026-10-15. A trusted local CLI bootstraps the first support admin;
admin endpoints issue one-use invitations and manage grants/disable access.
Expiring revocable sessions, password reset, tenant/role guards, and browser
signup/login preserve the existing application access policy. Admin capability
does not grant report access. Explicit legacy demo mode retains test fixtures;
password mode never falls back to them. Kevin accepted final PAIR implementation
review on 2026-10-18; RF-702 is DONE within this scope. Hands-on deployment
verification remains separate.

Verification on 2026-10-15: `pnpm check` passed formatting/lint,
generated-client drift, Python/TypeScript checks, production build, all 794
backend tests, and all 192 frontend tests with no skips on disposable PostgreSQL.
The 13 account lifecycle cases and eight new browser interaction cases passed.
Migration `0007` upgrade/rollback and ORM drift passed in a separate disposable
database; CLI help and documentation links/whitespace passed. The first full run
hit the previously recorded checkpoint restart flake; it passed in isolation
and in the full rerun without changes to that test. The project database is
unchanged. No live providers or hands-on browser verification were used.

RF-704 is DONE after Kevin accepted final PAIR review on 2026-10-18.
Its goal and acceptance criterion are to trace requests, workflow runs, model
calls, and tools without unsafe data. It builds on RF-701's log threat analysis,
RF-702's authentication boundaries, and RF-703's durable execution identifiers.
The learning objective is to connect asynchronous work through correlation IDs
while keeping operational logs separate from saved workflow history. The
[logging contract](structured-logging.md) records Kevin's approved metadata-only
JSON stdout scope, with host-managed collection/search/retention. Implementation
adds request correlation, authorized operation IDs, model attempts, durable tool
phases, and safe server/SDK output through `api.server`. No local viewer or
external collector is added. The database-backed correlation test passed after
Docker became available on 2026-10-18. Kevin accepted the verified implementation
on the same date.

Initial verification on 2026-10-18: `pnpm check` passed formatting/lint,
generated-client drift, Python/TypeScript types, production build, 606 backend
tests, and 192 frontend tests. Docker/PostgreSQL was unavailable in WSL;
215 database-dependent tests were skipped. The
26 logging cases passed, including a real ephemeral Uvicorn process, concurrent
request isolation, streaming interruption, retries, embedding timeouts, refusal,
server/SDK secret exclusion, and quiet CLI imports. A 62-case focused logging,
embedding, and evidence suite passed separately. The added real PostgreSQL
approval/recovery correlation test was collected but skipped in that initial run.
Documentation links/whitespace and the single NEXT ticket passed. No live provider
calls, project database changes, external log service, or deployment were performed.

Follow-up verification on 2026-10-18 after Docker became available: `pnpm check`
passed all 821 backend tests and 192 frontend tests with no skips, plus
formatting/lint, generated-client drift, Python/TypeScript types, and production
build. The new PostgreSQL-backed logging test also passed separately. It confirms
that approval and recovery have different request IDs, retain run/execution IDs,
and reuse a committed destination receipt without a second dispatch. Tests used
a disposable PostgreSQL 17/pgvector container with isolated schemas; the project
database is unchanged. The database blocker is closed, and Kevin accepted final
PAIR review on 2026-10-18.

RF-705 is DONE after Kevin accepted final PAIR review on 2026-10-18.
Its goal and acceptance criterion are to persist model, prompt, token usage,
latency, retries, and estimated cost per run. It builds on RF-509's limited
latest-extraction view, RF-511's durable intake operations, RF-506's separate
evidence operations, RF-702's access rules, and RF-704's correlation IDs.
Kevin selected versioned pricing configuration and stopping before live dispatch
when a durable accounting start cannot be saved. The
[accounting contract](model-accounting.md) records the scope and remaining limits.
The learning objective is to retain actual attempts across retries/restarts and
make incomplete measurements visible instead of treating missing usage as zero.
Implementation is verified: migration `0008`, durable per-attempt records for
intake/evidence/embedding requests, frozen pricing snapshots, explicit
unknown/legacy coverage, and a separate support history with per-scope totals.
RF-509's latest-extraction view is preserved. Kevin accepted final PAIR review
on 2026-10-18.

Verification on 2026-10-18: final `pnpm check` passed formatting/lint,
generated-client drift, Python/TypeScript checks, production build, all 838
backend tests, and all 203 frontend tests with no skips on disposable PostgreSQL
17/pgvector. Seventeen accounting cases cover prices/unknowns, separate commits,
retries and rounds, process exit, failed start/completion writes, version changes,
embedding batches, partial response usage, timeout/cancellation, and protected
read-only HTTP history. Eleven browser interaction cases cover partial and zero
estimates, offline labeling, invalid/report-mismatched records, stale recovery,
access loss, explicit loading, and late session responses. Migration `0008`
upgrade/rollback and ORM drift passed in a separate disposable database. The
project database is unchanged. No live provider calls, real billing comparison,
production-browser walkthrough, or deployment were performed.

RF-706 is DONE after DELEGATE implementation and verification on 2026-10-18.
Kevin approved shared PostgreSQL counters. The [request-limit contract](request-limits.md)
records the 64 KiB body cap, upload deadline, configurable address/user/account/
model-operation limits, explicit HTTP errors, and remaining deployment limits.
Atomic reservations precede endpoint work, including across independent workers;
blocked model operations create no run and dispatch no provider call. The
supported server ignores forwarded address headers; reverse-proxy callers share
the proxy's address allowance. Concurrent-work/storage/spend quotas remain separate.

Final `pnpm check` passed formatting/lint, generated-client drift, Python/TypeScript
checks, production build, all 864 backend tests, and all 206 frontend tests with
no skips on disposable PostgreSQL 17/pgvector. Twenty-six new backend cases cover
input boundaries, counter concurrency/expiry/cleanup, HTTP and model-operation
rejections, access and token/account isolation, and invalid configuration. Three
new frontend cases verify clear errors without repeating requests. Migration
`0009` upgrade/rollback and ORM drift passed separately. The project database is
unchanged; no live provider calls or deployment were performed. RF-707 followed
this work and is now complete.

RF-707 is DONE after DELEGATE implementation and verification on 2026-10-18.
The [container contract](container-startup.md) records pinned images, the fixed
web workspace build, one-shot migrations/checkpoint setup under an advisory
lock, schema-gated readiness, and startup order. Application containers run as
non-root with read-only roots; the existing local data volume is preserved.

Full `pnpm check` passed formatting/lint, generated-client drift, Python/TypeScript
checks, production build, all 871 backend tests, and all 206 frontend tests with
no skips on disposable PostgreSQL. Seven startup cases cover fresh/concurrent
initialization, preserved data, old/unknown application revisions, missing/old
checkpoint versions, failed migrations, and sanitized failures. The isolated
`pnpm docker:smoke` passed real image builds, failed-initialization gating, fresh
health/startup order, runtime permissions, volume persistence, and database
outage/recovery including a database-backed authentication request. Final
focused type checks passed after that assertion was added. Tests removed their
own temporary containers and volumes; the project database is unchanged.
No live model calls, user provisioning, or deployment were performed.
RF-708 followed this work and its implementation is now complete.

RF-708 is DONE for the implemented and locally verified workflow under DELEGATE
ownership on 2026-10-18. The [CI contract](continuous-integration.md) records
GitHub Actions jobs for repository checks with PostgreSQL, offline fixture
execution/scoring/judging/reporting, container integration, and retained reports.
Actions are pinned to verified commits, repository permissions are read-only,
and provider/deployment secrets are not configured.

Actionlint 1.7.12 accepted the workflow; configured inputs match the pinned
official action definitions. Local replay of its exact shell steps passed
frozen/locked installs, formatting/lint, generated-client drift, Python/TypeScript
checks, production build, all 871 backend tests with zero skips, all 206 frontend
tests, and the fixture pipeline. All 20 cases completed without executor errors;
123 deterministic checks passed, six semantic checks remained unmeasured, and
fixture judging retained 15 unmeasured checks with no failures/errors. The
container integration command also passed. Reports are available locally in
ignored `artifacts/` for review. Disposable resources were cleaned up; the
project database is unchanged. No live provider calls or deployment occurred.
The first GitHub-hosted run remains unverified until the changes are committed
and pushed; neither a commit/push nor repository-setting changes were performed.
RF-709 is DONE; RF-710 is NEXT.

Kevin narrowed RF-709 on 2026-10-18: the stack supports learning current AI
workflows; the ticket does not require a formal defense of each library.
The [decision guide](architecture-decisions.md) links existing approval,
execution-recovery, retrieval, and evaluation rationale instead of duplicating
those contracts. Kevin accepted final PAIR review on 2026-10-18; RF-709 is DONE.
All 127 checked local documentation links resolve, whitespace checks pass, and
the roadmap has exactly one NEXT ticket. RF-710 follows the completed container,
authentication, safety, accounting, request-limit, CI, and decision work. Hosting
and configuration choices remain Kevin-owned under PAIR; deployment has not started.

Kevin changed RF-701, RF-703, and RF-709 from HAND to PAIR on 2026-10-15.
These tickets follow the [PAIR agreement](working-agreement.md#pair).

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-701 | Create threat model | PAIR | DONE | Required threat areas analyzed; Kevin accepted final security review on 2026-10-18. Remaining gaps are explicit; see threat-model.md |
| RF-702 | Add authentication and authorization | PAIR | DONE | Permanent invitation onboarding, repeat login, and access management implemented and tested; Kevin accepted final PAIR review on 2026-10-18. See authentication-and-access.md |
| RF-703 | Enforce tool idempotency | PAIR | DONE | Approved durable simulation prevents duplicate effects across repeated/recovered execution; Kevin accepted final PAIR review on 2026-10-18. Real external effects require a destination contract; see tool-idempotency.md |
| RF-704 | Add structured correlated logging | PAIR | DONE | Metadata-only request/run/model/tool logs verified; 821 backend and 192 frontend tests passed without skips. Kevin accepted final PAIR review on 2026-10-18; see structured-logging.md |
| RF-705 | Record model cost and performance | PAIR | DONE | Durable per-attempt model/prompt/usage/latency/retry records and versioned estimates implemented with explicit partial/legacy coverage; all checks pass. Kevin accepted final PAIR review on 2026-10-18; see model-accounting.md |
| RF-706 | Add rate and input limits | DELEGATE | DONE | Shared PostgreSQL rate counters, bounded uploads, and client-visible errors verified on 2026-10-18; all 864 backend and 206 frontend tests passed without skips, plus migration roundtrip/drift. See request-limits.md |
| RF-707 | Harden container startup | DELEGATE | DONE | Pinned images, one-shot schema initialization, readiness/startup order, and non-root runtimes verified on 2026-10-18. All 871 backend and 206 frontend tests passed without skips, plus real Docker smoke; see container-startup.md |
| RF-708 | Add continuous integration | DELEGATE | DONE | Workflow validated and commands replayed locally on 2026-10-18: all 871 backend/206 frontend tests, fixture pipeline, and container smoke passed. First GitHub-hosted run awaits a push; see continuous-integration.md |
| RF-709 | Record consequential architecture choices | PAIR | DONE | Stack learning goal and consequential choices recorded through existing contracts; documentation links/whitespace verified. Kevin accepted final PAIR review on 2026-10-18; see architecture-decisions.md |
| RF-710 | Deploy the demonstration | PAIR | NEXT | Public demo uses safe simulated actions and documented configuration |

Kevin selected Railway Hobby on 2026-10-18. The
[deployment runbook](railway-deployment.md) and per-service variable templates
prepare the existing images for hosting. On 2026-10-19 the authenticated CLI
provisioned private pgvector storage and the API, reused the existing web
service, and configured Docker builds, schema initialization, HTTPS, and offline
password-mode operation. All three deployments succeeded; public web, API
liveness/readiness, anonymous access denial, CORS, and browser-bundle API-origin
checks passed. Web readiness uses `/reports` because `/` redirects. Budget
limits, administrator setup, fictional demo records, and authenticated
browser/restart verification remain pending. RF-710 stays NEXT.

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
7. Evaluation baseline and measured design comparison
8. Hardened, deployed portfolio demonstration
