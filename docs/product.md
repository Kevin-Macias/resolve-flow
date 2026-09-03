# ResolveFlow product brief

## Problem

Customers often cannot tell whether a technical problem is already known,
whether somebody is working on it, or what information support needs from them.
Support engineers then receive incomplete reports and must manually classify
their impact, search runbooks and past incidents, ask for missing information,
and translate the findings into actionable internal work. This is repetitive,
but unsafe to automate without access controls, evidence, auditability, and
human control.

## Product

ResolveFlow is an AI support and incident intake platform with two connected
experiences: a customer assistant and an internal support workspace. A customer
or support engineer can submit an unstructured issue such as:

> Payments sometimes remain pending after a successful Stripe checkout.

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

## MVP demonstration

The first complete demonstration must take less than five minutes:

1. A simulated authenticated customer reports an ambiguous payment problem.
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
- Simulated customer identity and tenant context
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
- Production identity management; the MVP uses explicit simulated identities
- Large-scale document crawling
- Multi-agent orchestration
- Training or fine-tuning a model
- Native mobile applications

## Example user journeys

### 1. Existing issue status

A customer asks why a reported export problem is still open. ResolveFlow
verifies the simulated customer context, finds that customer's ticket, and
returns its public status and latest customer-visible update. It does not expose
internal comments, assignees, or similar tickets owned by other customers.

### 2. Known incident match

A customer reports that payments remain pending. ResolveFlow finds an active
customer-visible incident affecting the payment service, asks for the minimum
information needed to determine whether it applies, and links the report rather
than creating a duplicate ticket. The internal workspace records the match and
supporting evidence.

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
