# Workspace information architecture (RF-501)

Status: approved by Kevin in the RF-501 PAIR review on 2026-10-09.

This document records the RF-501 design and its original readiness assessment.
For current implementation, see [customer CRUD](customer-report-screens.md) and
[customer intake endpoints](customer-intake-runs.md). Internal support reads
still require a separate reviewed contract.

## Purpose and scope

Help a support engineer answer three questions: what did the customer report,
what do we know, and what needs a human decision? The initial demonstration
troubleshoots a missing issue report using ResolveFlow's own submission and
visibility behavior.

RF-501 defines navigation, layout, and display states for later implementation.
UI labels distinguish issue reports, support tickets, and known incidents using
the [domain language](domain-language.md).

## Approved navigation

Use a report list and a report detail page. Keep customer and support experiences
separate, with an explicit simulated identity indicator in the MVP. A UI role
switch is not authorization; application code establishes and checks access.

| Experience | Entry and destination | Information available |
| --- | --- | --- |
| Customer | My reports → New report or Report detail | Own original report, permitted edits/archive, clarification, summary confirmation, and customer-safe updates as integrations become available |
| Support | Report queue → Report workspace | Authorized report, internal analysis, evidence, proposed action and approval, execution history, and call metrics |

Navigation names leave URLs/API contracts open. Support needs an authorized
cross-account read contract; the customer list cannot serve its queue.
RF-502 can begin with existing customer CRUD.

The report list shows title, affected service when supplied, report status, and
updated time. Open a row to inspect it; keep long descriptions on the detail
page. Do not show inferred cause or workflow progress as persisted report status.
Provide a clear empty state and a New report entry for customers.

## Support workspace layout

Use one detail page with section links. Summary and diagnosis occupy the main
column; evidence occupies an adjacent column. Actions appear below diagnosis,
with the full proposal visible before approval. Timeline and metrics follow.

```text
Report queue / Missing issue report                     Internal support
Report identifier · affected service · report status
Run: awaiting approval              Connection: connected

Summary | Questions | Diagnosis | Actions | Timeline | Metrics

+--------------------------------------+-----------------------------+
| Summary                              | Evidence                    |
| Customer's original observation      | Source title and revision   |
| Extracted summary, tentative severity| Heading and line range      |
|                                      | Exact excerpt               |
| Questions and previous answers       | Supports / contradicts      |
| Unresolved gaps and contradictions   | Fictional example label     |
|                                      |                             |
| Diagnosis                            | Selecting a citation brings |
| Supported claims / inferences        | its source into view        |
| Missing evidence / conflicting claims|                             |
|                                      |                             |
| Proposed action and approval         |                             |
| Arguments · reason · effect · risk   |                             |
| [Approve this version] [Reject]      |                             |
+--------------------------------------+-----------------------------+
| Timeline: saved transitions in order                                |
| Metrics: model calls, usage, duration, estimated cost when available  |
+--------------------------------------------------------------------+
```

This is the target page. Render each section when its application data becomes
available; evidence, proposals, and approval require their own integrations.

On narrow screens, stack summary, questions, diagnosis, evidence, actions,
timeline, and metrics. Citation links focus the source and link back to the claim.
Use text labels, keyboard-accessible controls, and visible form errors. Preserve
answers on disconnection and check saved state before resubmitting.

## Placement and meaning

| Area | What the engineer sees | Source and boundaries |
| --- | --- | --- |
| Summary | Original customer description, extracted summary, service, tentative severity, reported facts | Issue report plus validated extraction; distinguish customer observations from model interpretation |
| State | Report status and workflow progress shown separately; connection state beside progress | Current authorized application snapshot; events explain history but do not replace current state |
| Questions | Current questions, accepted previous answers, round count, unresolved gaps, and incomplete-continuation label | Saved clarification contract; customer answers in the customer experience, support initially reads them |
| Evidence | Source title, revision, heading/lines, exact excerpt, visibility, fictional label, and retrieval rank/metric when supplied | Verified citations and retrieval data; similarity is not a probability or proof of correctness |
| Diagnosis | Supported claims, inference, missing evidence, and conflict with explanations and citation links | Validated claim/citation report when integrated; current preliminary diagnosis must show cause unknown and evidence unavailable |
| Actions | Proposed tool, exact arguments, reason, expected effect, risk, version, and simulated effect label | Saved immutable proposal, separate from generated diagnosis prose |
| Approval | Approve/reject the displayed proposal version; accepted decision and execution outcome shown separately | Application-authorized support decision bound to the exact proposal; detailed interaction design belongs to RF-507 |
| Timeline | Ordered saved intake and approval transitions, timestamps, outcomes, and incomplete/unknown-outcome labels | RF-310 combined timeline, preserving event IDs and stage order; no reconstructed chat history |
| Metrics | Model, prompt version, attempts, tokens, measured duration, and estimated cost with its basis when available | Recorded call data; missing measurements display “Not available,” never fabricated zero values |

Keep original observations available even after extraction or clarification.
Customer summary confirmation and internal action approval are distinct steps.
Do not expose internal evidence or diagnosis through a collapsed customer panel;
customer responses require an application-owned safe projection.

## States and interactions to preserve

The labels below describe display behavior, not new backend enum values.
Map the eventual transport contract explicitly before implementing them.

| Situation | Display and next step |
| --- | --- |
| Loading or no run | Show report loading separately from analysis loading; a report without a run says analysis has not started |
| Waiting for clarification | Customer sees saved current questions and allowed continuation; support sees that customer input is pending |
| Clarification limit or incomplete continuation | Keep unresolved gaps visible; offer only continuation allowed by the saved pause, with no invented third round |
| Summary needs confirmation | Customer reviews the structured summary; this is not approval to execute a tool |
| No evidence or unresolved cause | State that evidence is unavailable or insufficient; keep inference separate and do not invent a diagnosis |
| Retrieval unavailable | Distinguish retrieval failure from a successful search with no results; expose only supported recovery actions |
| Awaiting approval | Show the complete saved proposal and its version with decision controls only for authorized support |
| Proposal changed or decision stale | Refresh the proposal, explain that a fresh review is needed, and do not carry approval forward |
| Approved, execution pending | Show approval receipt and pending execution separately; do not claim a ticket exists |
| Rejected | Show rejection and no execution; no automatic re-proposal or new workflow run |
| Simulated execution succeeded | Explicitly label the simulated result; its identifier does not imply a persisted real support ticket |
| Tool failed or outcome unknown | Preserve the accepted approval and unknown outcome; do not offer blind retry of a possibly completed effect |
| Disconnected or reconnecting | Retain the last saved view with a stale-data notice; reconcile current state before enabling decisions again |
| Access denied or report unavailable | Hide protected data and show a safe unavailable state; a customer 404 is not proof of archival |

The current graph has no HTTP confirmation handler, retrieval stage, or general
retry endpoint. Those controls must wait for reviewed application operations.
No archive restoration or archive actor/time history is proposed here.

## Backend readiness and implementation order

The current frontend at `apps/web/src/routes/index.tsx` only checks API health.
Existing API routes support customer-scoped report create/list/read/update/archive.
Workflow, clarification, approval, citations, and timeline contracts exist in
Python but are not exposed through workspace HTTP endpoints.

| Planned UI work | Existing foundation | Integration still needed |
| --- | --- | --- |
| RF-502 customer report CRUD | IssueReport endpoints and generated TypeScript client | Query/cache setup, forms, detail/list states, explicit simulated identity binding |
| Support queue and workspace reads | Report persistence and internal Python contracts | Reviewed support list/detail/run projection with authorization; RF-512 covers scoped current report-state lookup, not a complete queue/run API |
| RF-503/504 progress and timeline | Checkpoints and combined persisted events | Authorized run snapshot, stream/reconnect transport and server lifecycle integration |
| RF-505 clarification | Saved pauses, bounded rounds, and accepted turns | Authorized answer/resume operation, customer projection, and separate confirmation integration |
| RF-506 evidence and diagnosis | Retrieval, citation assembly, and RF-411 analysis boundary | Separate saved preliminary support analysis and authorized evidence panel implemented under the 2026-10-13 approved scope; customer confirmation and automatic workflow diagnosis remain separate |
| RF-507/508 approval | Immutable proposals, guarded runner, and simulated execution | Approved manual support simulation API and controls implemented and verified; Kevin accepted RF-508 final PAIR review on 2026-10-13. Customer confirmation and automatic proposal generation remain separate |
| RF-509 metrics | Latest extraction record saved in intake checkpoints | Authorized saved-record display implemented within the approved 2026-10-13 scope; latency/cost explicitly not recorded. Full call history and accounting remain RF-705; see execution-metrics-ui.md |

Start RF-502 with the approved customer CRUD contract. Scope missing support
integrations with Kevin as tickets or reviewed expansions, separately from SSE.
Label mock data clearly so planned sections cannot be mistaken for live results.

## Review walkthroughs

1. **Ordinary report CRUD:** customer creates a report, opens it from My reports,
   edits permitted fields, and archives it with confirmation. An empty list and
   unavailable detail remain understandable without any workflow run.
2. **Missing report investigation:** customer provides clarification; support
   reads observations, examines source excerpts, and distinguishes possible
   causes from verified state. Until RF-512 supplies an authorized lookup, the
   workspace cannot claim that the missing report was archived.
3. **Human decision:** support reviews a saved simulated ticket proposal,
   approves its exact version, and sees approval followed by the saved simulated
   result. Rejection and stale approval remain distinct outcomes.
4. **Interrupted or failed run:** reconnect restores saved state and timeline;
   unanswered questions, missing evidence, and unknown execution outcomes remain
   visible without repeating a consequential action.

Kevin approved the single-page layout, customer/support navigation, read-only
support clarification view, and implementation sequence on 2026-10-09. Local
documentation links and whitespace checks passed. RF-501 is DONE; RF-502 is NEXT.
This is an approved design; the screens and missing integrations remain to be
implemented. This documentation change introduces no runtime code or model calls.
