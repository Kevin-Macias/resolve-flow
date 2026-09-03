# ResolveFlow domain language

> Status: Approved in RF-002.

## Naming principle

Use different terms for what a customer reports, what support tracks, and what
is actually happening in the service. Treating all three as an "incident"
would make status, ownership, deduplication, and visibility ambiguous.

## People and access

### Customer

A person using ResolveFlow to report a problem or view information available to
their organization. A customer is always associated with one customer account
in the MVP.

### Support engineer

An internal operator who reviews reports, internal evidence, diagnoses, and
proposed actions. Support engineers can see internal information that customers
cannot.

### Customer account

The organization boundary that owns customer reports. This is the tenant
boundary: one account must never read another account's private data.

### Request context

Application-established identity, role, customer account, and permissions for
one request. It is not supplied or modified by the model. `RequestContext` is
preferred over `CustomerContext` because internal users also make requests.

## Support domain

### Issue report

The customer's original description of an observed problem plus submitted
metadata. It preserves what the customer said and does not claim that the cause
or impact has been verified.

An issue report belongs to exactly one customer account and records its
submitting customer. It can be linked to one or more possible support tickets;
the link records whether each match is suspected, confirmed, or rejected.

### Support ticket

The durable internal unit of investigation or work. A support ticket is owned
by a support team, may be assigned to an engineer, and can aggregate reports
from many customers or accounts. It contains the normalized summary, workflow
status, customer-visible updates, and internal work. The MVP creates this record
inside ResolveFlow rather than in an external issue tracker.

`SupportTicket` is preferred in code over the generic `Ticket`.

### Report-ticket link

The relationship between an issue report and a possible support ticket. It
records match status (`SUSPECTED`, `CONFIRMED`, or `REJECTED`), who or what made
the link, confidence when model-assisted, reason, and timestamps. Keeping this
as a first-class record supports review and impact reporting without treating a
model suggestion as fact.

### Known incident

A verified service-level event that may affect multiple customers, such as a
payment outage. Multiple issue reports and support tickets can link to one known
incident. Only explicitly published incident fields are customer-visible.

`KnownIncident` is preferred over `Incident` to avoid confusing it with an
unverified customer report.

### Support team and assignment

The support team operationally owns a ticket. An optional assigned engineer is
responsible for its current progress. Creation, assignment, and approval are
separate facts: approving ticket creation does not make the approver its owner.

### Clarification

A targeted question and its answer used to fill a specific information gap. It
records who asked, who answered, ordering, and timestamps. A clarification is
part of a workflow run and may update the normalized ticket data without
overwriting the original issue report.

## Knowledge and reasoning

### Knowledge document

A versioned source available for retrieval, such as a runbook, public help
article, or historical incident. Its metadata declares source, version, and
visibility before its contents can be retrieved.

### Evidence

A ranked excerpt from an authorized knowledge document that was actually used
to support or challenge a claim. Evidence retains a stable source location and
visibility. Model-generated prose is never evidence.

### Diagnosis

A versioned assessment of likely cause, impact, uncertainty, and recommended
next steps. Each factual claim is linked to evidence or explicitly labeled as
an inference. A diagnosis is internal-only in the MVP.

## Workflow and actions

### Workflow run

One durable execution of the ResolveFlow process for a support ticket. It owns
workflow state, clarification progress, model calls, pauses, and its terminal
outcome. Retrying or resuming the same execution does not create a new run.

### Proposed action

A versioned request to invoke an application-owned tool with validated
arguments, an explanation, expected effect, risk, and idempotency key. A model
may propose it but cannot execute it.

### Approval

An internal support engineer's decision to approve or reject one immutable
version of a proposed action. Changing the action or its arguments invalidates
the approval.

### Tool execution

One application-controlled attempt to perform an approved action. It records
the validated input, outcome, error, and idempotency key. Approval and execution
are separate records because an approved action can still fail.

### Execution event

An append-only timeline fact describing a meaningful state transition, such as
`clarification_requested`, `diagnosis_created`, or `action_rejected`. It is for
audit and UI inspection; it is not the authoritative current state by itself.

## Visibility

Every record or field that can reach retrieval or an API response has an
application-controlled visibility classification:

| Visibility | Meaning | Example |
| --- | --- | --- |
| `PUBLIC` | Safe for anyone using the product | Published known-incident status |
| `CUSTOMER_ACCOUNT` | Visible only within the owning customer account | Customer's support ticket status |
| `INTERNAL` | Visible only to authorized support engineers | Runbook or diagnosis |

Visibility is enforced before retrieval and again when constructing a response.
The model may not promote a record or field to a broader visibility level.

## Relationships

```text
CustomerAccount
  `-- Customer
        `-- IssueReport
              `-- ReportTicketLink -- SupportTicket
                                          |-- owned by SupportTeam
                                          |-- assigned to SupportEngineer
                                          |-- Clarification
                                          `-- WorkflowRun
                                                |-- Evidence -> KnowledgeDocument
                                                |-- Diagnosis
                                                |-- ProposedAction -> Approval
                                                |                    `-- ToolExecution
                                                `-- ExecutionEvent

KnownIncident
  `-- many SupportTickets
```

A support ticket can have many report-ticket links, including reports from
different accounts. A report may temporarily have multiple suspected links,
but business rules can require at most one confirmed active match when that
becomes useful.

## Operational metrics

The relationship model supports manager-facing questions without exposing
customer details:

- Number of linked reports per ticket or known incident
- Number of distinct reporting customers
- Number of distinct affected customer accounts
- Suspected, confirmed, and rejected match counts
- Report volume over time
- Time from first report to internal acknowledgement or confirmed incident
- Ticket age, assignment, and workflow status

These values describe observed reports. They must not be presented as the true
number of affected people unless another reliable data source measures impact.

## Invariants to preserve

1. An issue report is an observation, not proof of an incident.
2. A support ticket is internally owned and may aggregate many customer reports.
3. Customer access to a ticket is derived from an authorized report link and a
   customer-safe projection, not ownership of the internal ticket.
4. A known incident may affect many accounts but exposes only published fields.
5. The original issue report remains unchanged after normalization.
6. Evidence must come from an authorized, identifiable source.
7. Diagnosis, evidence, and customer-visible status are separate representations.
8. Approval binds to one immutable proposed-action version.
9. Approval, assignment, and ownership remain separate relationships.
10. Tool execution is authorized and idempotent independently of model output.
