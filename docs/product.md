# ResolveFlow product brief

## Problem

Customers need to know whether a problem is known, who is working on it, and
what information support needs. Support engineers receive incomplete reports,
assess impact, search runbooks and past incidents, ask questions, and plan work.
Automating this requires access controls, evidence, an audit trail, and human
approval.

## Product

ResolveFlow is an AI support and incident intake platform with two connected
experiences: a customer assistant and an internal support workspace. A customer
or support engineer can submit an unstructured issue such as:

> I submitted an issue report, but I can't find it in my list.

ResolveFlow then:

1. Determines whether the user wants to check an issue or report a new one.
2. Searches only the records that user is authorized to see.
3. Returns a customer-safe status when a matching issue already exists.
4. Otherwise extracts facts and asks targeted clarification questions.
5. Searches public knowledge, internal runbooks, and similar incidents within
   the access policy of the current user.
6. Gives the support engineer a cited diagnosis, classification, and action
   plan in the internal workspace.
7. Shows any consequential tool call and asks for approval of the exact action.
8. Creates a structured ticket in ResolveFlow after approval.
9. Stores a complete execution history and exposes only customer-safe updates.

## Users

- **Customer:** wants to identify a known problem, check the status of their own
  issue, or submit a useful new report without repeating information.
- **Support or incident engineer:** wants to triage incoming reports quickly
  while retaining responsibility for internal conclusions and consequential
  actions.

An **access administrator** is a support user who can invite users and manage
access. This capability does not grant report access; support account grants
remain explicit.

[Invitation onboarding](authentication-and-access.md) creates permanent users
with a fixed role and scope. Users sign in again with email/password. Sessions
expire and can be revoked; static fixtures require explicit legacy demo mode.

## MVP demonstration

The first complete demonstration must take less than five minutes:

1. An authenticated customer reports that a previously submitted
   issue report is missing from their list.
2. ResolveFlow checks public incidents and that customer's tickets, then asks a
   clarification question because it cannot safely identify a match.
3. The customer answers and confirms the structured report.
4. A support engineer opens the report, inspects internal evidence, and reviews
   the cited diagnosis and proposed ResolveFlow ticket.
5. The support engineer approves the exact proposed action.
6. ResolveFlow creates the simulated ticket, displays the complete internal
   timeline, and gives the customer a safe status update.

## Product principles

- The model proposes actions; application code validates and executes them.
- External writes require approval of the exact action and arguments.
- Authorization and data scoping happen before context reaches the model.
- Customers can access public information and their own records, never another
  customer's records or internal-only material.
- Retrieved documents are evidence and untrusted input, not instructions.
- Unsupported facts and model inferences must be distinguishable from evidence.
- Workflow state must survive interruption and be inspectable.
- Important behavior must be measured with repeatable evaluations.

## MVP scope

- Issue-report CRUD
- Invitation-only permanent accounts, email/password login, and tenant context
- Customer issue intake and own-ticket status lookup
- Matching against customer-visible known incidents
- Structured extraction and classification
- Clarification loop with a fixed upper bound
- Retrieval over a small curated runbook and incident collection
- Diagnosis and action plan with source citations
- Internal support workspace
- One simulated ResolveFlow `create_ticket` tool
- Approval, rejection, resume, and idempotent execution
- Execution timeline, model usage, latency, and estimated cost
- Evaluation dataset and regression report

## Non-goals for the MVP

- General-purpose chat
- Autonomous remediation
- Production integrations with external issue trackers, payment providers, or
  cloud providers
- Enterprise identity integration, SSO, MFA, and automated invitation delivery
- Large-scale document crawling
- Multi-agent orchestration
- Training or fine-tuning a model
- Native mobile applications

## Example user journeys

### 1. Existing issue status

A customer asks whether support is investigating their missing report.
ResolveFlow checks the current identity and returns only that customer's
ticket status and latest customer-visible update. Internal comments, assignees, and other
customers' tickets stay private.

### 2. Known incident match

A customer reports trouble submitting issue reports. In this planned journey,
ResolveFlow finds a published incident, asks enough questions to check whether
it applies, and links the report to avoid a duplicate ticket. The internal
workspace records the match and evidence.

### 3. New issue requiring internal review

A customer reports an intermittent problem that has no authorized match.
ResolveFlow asks targeted questions and lets the customer confirm the structured
summary. A support engineer reviews internal runbooks and similar incidents,
corrects the proposed severity if necessary, and approves creation of a new
ResolveFlow ticket. The customer receives only its public identifier and status.

## Success criteria

- A new developer can run the system from the root README.
- All persisted and API-facing data has typed contracts.
- Ordinary automated tests never require a live model call.
- No consequential tool executes without valid, current approval.
- Customer responses never contain another customer's data or internal-only
  evidence.
- Every diagnosis identifies its evidence and any unsupported inference.
- Evaluation results compare at least one design change against a baseline.
- The repository explains architectural decisions and known limitations.

## Initial retrieval scenario

RF-401 focuses on ResolveFlow issue-report submission and visibility, grounded
in the existing API. The [feature summary](issue-report-troubleshooting.md)
explains the behavior and troubleshooting distinctions. Historical investigations
will be fictional fixtures. The end-to-end assistant and workspace remain planned.

RF-512 now provides an authorized [support report-state lookup](support-report-state.md)
that can confirm current archival within granted accounts. Connecting it to the
support UI and diagnosis remains separate work; customer 404 responses alone
still cannot confirm archival. Archive history and restoration remain future work.

PDF ingestion is deferred beyond the MVP. The initial retrieval corpus is
Markdown-only; document ingestion, retrieval, and citations remain in MVP scope.

The approved [workspace information architecture](workspace-information-architecture.md)
places summary, questions, diagnosis, evidence, action approval, timeline, and
metrics around an issue report. Kevin approved RF-501 on 2026-10-09; the design
keeps customer-safe views separate from the internal support workspace.

Customer intake now has account-scoped start/read/clarification/recovery HTTP
operations and read-only SSE over durable projections. The default is explicitly
labeled offline simulation. Intake ends at needs-confirmation or failure; summary
confirmation, evidence-backed diagnosis, and support workflow operations remain planned.
An internal support read endpoint now exposes saved intake timelines within
explicit account grants, including archived reports. A separate
[support timeline page](execution-timeline-ui.md) now opens a known report ID
and shows saved intake history with refresh and access-loss states. Its
database-backed browser verification passed on 2026-10-12. The support queue and
workflow mutations remain planned; see [support run reads](support-run-reads.md).
Customer report details now offer [clarification controls](customer-clarification-ui.md),
accepted answer history, incomplete continuation, and explicit recovery. Their
database-backed browser verification passed on 2026-10-12. Setup and backend
limitations are in [customer intake runs](customer-intake-runs.md).

Support can explicitly request and inspect saved [preliminary evidence analysis](evidence-panel.md)
on the report page. Kevin approved this separate integration on 2026-10-13.
It labels observations as unconfirmed, preserves source provenance, and rechecks
current access. The default uses fixture ranking and scripted analysis; live
relevance and model injection resistance remain unmeasured. Customer summary
confirmation and automatic workflow diagnosis remain separate work.

Support can also author a simulated ticket proposal after intake finishes, then
approve or reject its exact saved version through
[support approval controls](support-approval-controls.md). Kevin approved this
scope and mutation access on 2026-10-13. The UI labels observations as unconfirmed
and preserves separate proposal, decision, and execution outcomes. It creates no
persisted support ticket. Customer confirmation and automatic proposal generation
remain separate. Kevin accepted RF-508's final PAIR implementation review on
2026-10-13.

The support API now saves [durable simulated operation receipts](tool-idempotency.md)
and offers an explicit recovery command for interrupted execution. Repeated
decisions and reads do not retry effects. Recovery retains the approved arguments
and key, checks current access and unchanged observations, and reuses the saved
destination result. This persists simulated effects, not real support tickets.
The existing support screen shows saved outcomes; recovery is an API operation.

Support also sees [metrics for the latest saved intake extraction](execution-metrics-ui.md):
configured model, prompt version, attempts, and token usage when returned. Kevin
approved this limited display on 2026-10-13. That snapshot retains its limited
scope and unavailable latency/cost fields. A separate
[model attempt history](model-accounting.md) adds durable intake/evidence records,
measured provider time, and versioned cost estimates with partial and unavailable
states. Offline activity remains labeled; estimates are not provider bills.

Operators can trace requests through workflow, model, and simulated tool events
using [metadata-only JSON logs](structured-logging.md). Sensitive content stays
out of operational logs; hosting supplies collection and search. These logs
support diagnosis and do not replace saved workflow history or effect receipts.

[Request limits](request-limits.md) bound upload size and request frequency.
Rejected work returns clear errors and a retry delay when rate allowance is
exhausted. Model-operation limits preserve a separate allowance for saved reads;
actual provider usage remains in the accounting history.
