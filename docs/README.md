# ResolveFlow project documentation

Keep planning, decisions, and progress here, alongside the code.
[`AGENTS.md`](../AGENTS.md) defines how Codex handles tickets, ownership, and
"What's next?" requests.

## Documents

| Document | Purpose | Update when |
| --- | --- | --- |
| [Product brief](product.md) | Defines the problem, users, scope, and demo | Product behavior or scope changes |
| [Architecture](architecture.md) | Describes what exists and where the design is going | Components, boundaries, or data flow change |
| [Architecture decisions](architecture-decisions.md) | Records the stack's learning goal and links consequential application choices | Decision rationale or its limits change |
| [Threat model](threat-model.md) | Maps trust boundaries, attacks, existing defenses, and remaining security work | Access, provider data flow, tools, storage, or deployment exposure changes |
| [Authentication and access](authentication-and-access.md) | Defines invitation onboarding, repeat login, admin setup, and access rules | Identity, account permissions, or revocation behavior changes |
| [Structured logging](structured-logging.md) | Defines RF-704 JSON fields, correlation, supported startup, and host-managed collection | Logging policy or trace boundaries change |
| [Model accounting](model-accounting.md) | Defines RF-705 durable attempts, versioned estimates, incomplete totals, and access rules | Model accounting or pricing behavior changes |
| [Domain language](domain-language.md) | Defines shared product terms and visibility boundaries | A domain concept or relationship changes |
| [Extraction contract](extraction-contract.md) | Defines validated issue-report extraction output | Extraction fields or semantics change |
| [Severity policy](severity-policy.md) | Defines tentative severity rules and examples | Impact classification rules change |
| [Clarification policy](clarification-policy.md) | Defines when to ask and how many questions to keep | Clarification triggers or limits change |
| [Prompt and model settings](prompt-and-model-settings.md) | Records extraction prompt version and model settings | Prompt text or model configuration changes |
| [Retry policy](retry-policy.md) | Defines provider timeouts, retryable failures, and attempt limits | Extraction failure handling changes |
| [Deterministic AI tests](deterministic-ai-tests.md) | Lists offline extraction scenarios and their limits | Test expectations change |
| [Live model check](live-model-check.md) | Explains the opt-in extraction check and its output | Live command or metrics change |
| [Provider boundary](provider-boundary.md) | Defines the OpenAI and fake model adapters | Provider behavior or interface changes |
| [Workflow state](workflow-state.md) | Defines durable and recomputable fields for each workflow stage | Workflow state or persistence boundaries change |
| [Workflow transitions](workflow-transitions.md) | Draws normal, pause, rejection, failure, and resume paths | Workflow routing or failure behavior changes |
| [Minimal workflow](minimal-workflow.md) | Explains the four-node graph, typed results, and integration boundary | Implemented graph behavior changes |
| [Workflow clarification](workflow-clarification.md) | Explains bounded rounds, human pause/resume, and incomplete continuation | Clarification workflow behavior changes |
| [Workflow checkpoints](workflow-checkpoints.md) | Explains PostgreSQL setup, typed snapshots, and restart restoration | Checkpoint storage or lifecycle changes |
| [Proposed actions](proposed-actions.md) | Defines immutable ticket proposals, revisions, risk, and idempotency keys | Action contracts change |
| [Action approval](action-approval.md) | Explains exact proposal binding, support decisions, and the approval pause | Approval behavior changes |
| [Approval experience](approval-experience.md) | Defines the approved support review card, decision confirmation, and saved outcomes | RF-507 design or approval UI behavior changes |
| [Support approval controls](support-approval-controls.md) | Defines RF-508's approved proposal/decision HTTP integration, mutation access, and verification | Support approval behavior or its integration changes |
| [Simulated ticket tool](simulated-ticket-tool.md) | Defines validated execution and deterministic fake ticket results | Tool execution behavior changes |
| [Durable simulated execution](tool-idempotency.md) | Defines operation intent, destination receipts, and explicit crash recovery | Execution persistence, recovery, or idempotency guarantees change |
| [Approval edge cases](approval-edge-cases.md) | Explains serialized submissions, duplicates, and safe failures | Approval submission behavior changes |
| [Execution timeline](execution-timeline.md) | Defines ordered, sanitized checkpoint events and restart behavior | Timeline contracts or transitions change |
| [Vector storage](vector-storage.md) | Defines durable knowledge revisions and pgvector storage | Knowledge storage or embedding profile changes |
| [Chunking strategy](chunking-strategy.md) | Compares fixed and heading-aware passages for the current corpus | Chunk boundaries or the selected strategy change |
| [Retrieval boundary](retrieval-boundary.md) | Defines typed search requests, ranked evidence, and the offline adapter | Retrieval contracts or eligibility rules change |
| [Retrieval integration](retrieval-integration.md) | Documents the selected LangChain embedding integration and PostgreSQL search | Retrieval integration scope or provider configuration changes |
| [Citations](citations.md) | Defines claim categories and source-backed citation validation | Claim attribution or citation contracts change |
| [Evidence panel](evidence-panel.md) | Defines saved preliminary support analysis, citation display, access, and verification | Evidence behavior or its integration changes |
| [Improvement experiment](improvement-experiment.md) | Records RF-607 approved prompt comparison, run limits, artifacts, and human review | Experiment design, scope, or interpretation changes |
| [Evaluation report](evaluation-report.md) | Generates readable evaluation results and compatible baseline comparisons | Report content, validation, or comparison rules change |
| [Rubric judging](rubric-judging.md) | Defines approved RF-605 semantic criteria, judge provenance, and review sequence | Rubric scope or judging contract changes |
| [Deterministic metrics](deterministic-metrics.md) | Scores fixture observations with explicit check counts, denominators, and semantic limits | Scoring behavior or report interpretation changes |
| [Evaluation runner](evaluation-runner.md) | Runs approved fixture cases and explains JSON observations, isolation, and execution status | Runner behavior or invocation changes |
| [Evaluation cases](evaluation-cases.md) | Records approved RF-602 scenarios, labels, fixtures, and validation limits | Evaluation cases or labels change |
| [Evaluation specification](evaluation-specification.md) | Defines approved RF-601 targets, case expectations, measurement limits, and review decisions | Evaluation scope or contracts change |
| [Retrieval tests](retrieval-tests.md) | Defines reviewed relevance cases, measurements, and baseline verification | Retrieval evaluation expectations or metrics change |
| [Document injection](document-injection.md) | Documents evidence-input defenses and structural attack tests | Untrusted evidence handling or defense expectations change |
| [Workspace information architecture](workspace-information-architecture.md) | Defines approved report navigation, workspace layout, display states, and integration dependencies | Workspace placement or navigation decisions change |
| [Customer report screens](customer-report-screens.md) | Explains customer CRUD screens, demo identity setup, and verification | Report UI or demo session behavior changes |
| [Customer clarification UI](customer-clarification-ui.md) | Explains saved questions, answer submission, incomplete continuation, recovery, and verification | Customer intake UI behavior changes |
| [Customer intake runs](customer-intake-runs.md) | Explains account-scoped intake endpoints, persisted snapshots, setup, and explicit recovery | Customer lifecycle contract or integration changes |
| [Support report state](support-report-state.md) | Defines authorized current-state reads including archived reports | RF-512 access or response contract changes |
| [Support run reads](support-run-reads.md) | Defines support account grants and read-only persisted intake timeline responses | Internal read access or response contracts change |
| [Execution metrics UI](execution-metrics-ui.md) | Defines latest saved extraction metrics, missing accounting, access, and verification | Metrics scope or display changes |
| [Execution timeline UI](execution-timeline-ui.md) | Explains the support timeline, session isolation, setup, and verification limits | Timeline UI scope or integration changes |
| [Workflow streaming](workflow-streaming.md) | Explains implemented SSE transport, safe snapshots, reconnect rules, and pending lifecycle integration | Streaming or run integration contracts change |
| [Frontend behavior coverage](frontend-tests.md) | Maps frontend behavior tests, regression gaps, and verification limits | Frontend coverage or test boundaries change |
| [Request limits](request-limits.md) | Defines upload bounds, shared rate counters, errors, configuration, and deployment limits | Input or request-rate policy changes |
| [Container startup](container-startup.md) | Defines image builds, initialization order, probes, volumes, and the isolated smoke test | Container startup or health contracts change |
| [Continuous integration](continuous-integration.md) | Defines workflow jobs, offline evaluations, reports, and local reproduction | CI checks, permissions, or runtime versions change |
| [Railway deployment](railway-deployment.md) | Defines demo service settings, variable templates, setup, and pending hosted verification | Railway setup or deployment evidence changes |
| [Roadmap](roadmap.md) | Tracks tickets, phases, ownership, and status | Work starts, finishes, or is reprioritized |
| [Working agreement](working-agreement.md) | Defines which work is for learning and which may be delegated | Collaboration rules change |

## Progress update checklist

When completing a ticket:

1. Verify its acceptance criteria and automated checks.
2. Change its status in `roadmap.md`.
3. Update `architecture.md` if the implemented design differs from it.
4. Record important tradeoffs in the ticket, commit, or a future architecture
   decision record.
5. Select only one new `NEXT` ticket so that the immediate learning objective
   remains clear.

The roadmap records product progress, but Git remains the source of truth for
the exact implementation history.
