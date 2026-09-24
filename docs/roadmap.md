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

**Milestone 1: tested IssueReport CRUD backed by PostgreSQL.**

RF-001 established the two-sided product and RF-002 defined its domain language,
access boundaries, and report aggregation model. RF-004 established the Python
quality baseline, RF-101 added validated issue-report schemas, RF-102 added a
tested application factory and system-readiness boundary, RF-103 defined the
initial relational design, RF-104 added async SQLAlchemy sessions with a test
override, RF-105 added the reviewed initial migration, and RF-106 added tested
customer-scoped create and read endpoints. RF-107 added reviewed, tested
customer service updates and soft archiving. The next ticket is RF-108: define
API error contracts.

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
| RF-108 | Define API error contracts | PAIR | NEXT | Validation, not-found, conflict, and unexpected errors share a documented shape |
| RF-109 | Add database integration tests | HAND | PLANNED | CRUD, validation, rollback/isolation, missing records, and transitions are covered |
| RF-110 | Generate TypeScript API client | DELEGATE | PLANNED | Repeatable generation produces a workspace package and drift can be detected |

## Phase 2 — Direct LLM integration

LangChain and LangGraph are intentionally excluded from this phase.

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-201 | Define extraction contract | HAND | PLANNED | Schema includes summary, service, severity, confidence, facts, missing data, and questions |
| RF-202 | Build the LLM provider boundary | HAND | PLANNED | OpenAI and deterministic fake providers satisfy one application-owned interface |
| RF-203 | Implement structured extraction | HAND | PLANNED | Validated output handles malformed, missing, refusal, empty, and SDK-error cases |
| RF-204 | Define severity policy | HAND | PLANNED | Written rules and examples prevent invented impact from raising severity |
| RF-205 | Version prompts and model settings | PAIR | PLANNED | Calls record prompt ID/version and model configuration |
| RF-206 | Implement clarification policy | HAND | PLANNED | Explicit rules identify missing or contradictory context and limit questions |
| RF-207 | Add timeout and retry policy | PAIR | PLANNED | Transient and permanent failures are distinguished; retries are bounded |
| RF-208 | Add deterministic AI tests | HAND | PLANNED | Default suite covers valid, ambiguous, malformed, timeout, refusal, and low-confidence cases offline |
| RF-209 | Add opt-in live model tests | PAIR | PLANNED | Separate command records shape, latency, and usage without exact-prose assertions |

## Phase 3 — Durable LangGraph workflow

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-301 | Design typed workflow state | HAND | PLANNED | Durable and recomputable fields are identified for every workflow stage |
| RF-302 | Document transitions and failures | HAND | PLANNED | Normal, clarification, rejection, provider failure, retrieval failure, and resume paths are drawn |
| RF-303 | Implement the minimal graph | HAND | PLANNED | Classify, evaluate, diagnose, and report nodes execute with typed state |
| RF-304 | Add bounded clarification branch | HAND | PLANNED | Workflow pauses/resumes, appends answers, limits loops, and permits incomplete continuation |
| RF-305 | Persist graph checkpoints | PAIR | PLANNED | A workflow resumes correctly after a process restart |
| RF-306 | Model proposed actions | HAND | PLANNED | Action includes tool, arguments, explanation, effect, risk, version, and idempotency key |
| RF-307 | Implement approval interrupt | HAND | PLANNED | Execution pauses and approval binds to exact immutable arguments |
| RF-308 | Implement simulated create-ticket tool | PAIR | PLANNED | Application code validates arguments and produces a deterministic fake result |
| RF-309 | Test approval edge cases | HAND | PLANNED | Stale, changed, duplicate, rejected, concurrent, resumed, and failed executions are safe |
| RF-310 | Persist execution timeline | PAIR | PLANNED | Ordered, sanitized events explain all meaningful state transitions |

## Phase 4 — Retrieval and citations

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-401 | Author curated knowledge dataset | HAND | PLANNED | Realistic runbooks include similar causes, stale advice, irrelevant text, and ambiguity |
| RF-402 | Define document metadata | HAND | PLANNED | Source, title, type, service, version, date, access class, and location are typed |
| RF-403 | Ingest Markdown documents | HAND | PLANNED | Parsing, hashing, idempotent re-ingestion, and errors are tested |
| RF-404 | Ingest PDF documents | PAIR | PLANNED | Empty pages, bad extraction, tables, and page citations are handled |
| RF-405 | Add pgvector schema and index | PAIR | PLANNED | Migration stores embeddings with documented index choice |
| RF-406 | Select chunking strategy | HAND | PLANNED | Fixed and heading-aware approaches are compared and the decision is recorded |
| RF-407 | Implement retrieval boundary | HAND | PLANNED | Framework-independent interface returns ranked typed evidence |
| RF-408 | Integrate selected LangChain pieces | PAIR | PLANNED | LangChain is limited to documented integration value, not domain contracts |
| RF-409 | Generate verifiable citations | HAND | PLANNED | Claims distinguish support, inference, missing evidence, and conflict by stable location |
| RF-410 | Add retrieval tests | HAND | PLANNED | Top-k relevance, exclusion, filters, duplicates, empty results, and stale sources are measured |
| RF-411 | Defend against document injection | HAND | PLANNED | Malicious document instructions cannot alter system or tool policy |

## Phase 5 — Incident workspace

| ID | Ticket | Owner | Status | Acceptance |
| --- | --- | --- | --- | --- |
| RF-501 | Design workspace information architecture | HAND | PLANNED | Summary, state, questions, evidence, diagnosis, actions, approval, timeline, and metrics are placed |
| RF-502 | Implement incident CRUD screens | DELEGATE | PLANNED | Typed client and TanStack Query support create, list, view, and update states |
| RF-503 | Implement SSE transport | PAIR | PLANNED | Ordering, duplicate events, event IDs, reconnect, and terminal state are tested |
| RF-504 | Implement execution timeline | DELEGATE | PLANNED | UI renders persisted events rather than reconstructing them from chat |
| RF-505 | Implement clarification UI | DELEGATE | PLANNED | Current questions, previous answers, submit state, and resume are visible |
| RF-506 | Implement evidence panel | DELEGATE | PLANNED | Each citation exposes source, location, relevance, and supporting text |
| RF-507 | Design approval experience | HAND | PLANNED | Exact action, arguments, reason, effect, risk, and reversibility are visible |
| RF-508 | Implement approve/reject controls | PAIR | PLANNED | Double submission, stale proposals, reconnects, and completed actions are safe |
| RF-509 | Display execution metrics | DELEGATE | PLANNED | Latency, model, tokens, cost estimate, and prompt version are shown |
| RF-510 | Add frontend tests | DELEGATE | PLANNED | Important loading, error, stream, evidence, clarification, and approval states are covered |

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
