# Workflow state design (RF-301)

One workflow run starts from an existing `IssueReport`. The run keeps its report
ID throughout intake, clarification, internal review, approval, and reporting.
`support_ticket_id` appears only if the approved create-ticket action succeeds.
A status lookup that does not create a report is a separate use case. Kevin
approved this design in the RF-301 PAIR review.

## State rule

Save answers and model proposals that must survive pause or restart unchanged.
Reference existing durable records: reload the original report by
`issue_report_id` instead of copying its description into the checkpoint.
Derive display text, routing flags, and prompts when needed. Every database read
and tool action checks current access; a checkpoint grants no permission.

The full shape below is an approved design sketch. RF-303 implements its minimal
subset in `apps/api/src/api/workflow/state.py`, with a derived clarification
decision and preliminary diagnosis; later-stage contracts remain planned.
RF-304 adds ordered `clarification_turns`, a saved `pending_clarification` with
questions and a stable pause ID, and `continued_incomplete`. The default in-memory
checkpointer supports pauses within one process. Inject RF-305's
[PostgreSQL checkpoints](workflow-checkpoints.md) for tested restart restoration.
Keep typed results in checkpoint state until durable application records own
them, then replace snapshots with record IDs through an explicit migration.

```python
class WorkflowState(TypedDict):
    workflow_run_id: UUID
    issue_report_id: UUID
    extraction: NotRequired[ExtractionResult]
    extraction_call: NotRequired[ExtractionCallRecord]
    clarification_turns: NotRequired[list[ClarificationTurn]]
    customer_confirmation: NotRequired[CustomerConfirmation]
    evidence: NotRequired[list[EvidenceSnapshot]]
    diagnosis: NotRequired[DiagnosisDraft]
    proposed_action: NotRequired[ProposedAction]
    approval: NotRequired[ApprovalDecision]
    tool_execution: NotRequired[ToolExecutionResult]
    support_ticket_id: NotRequired[UUID]
    customer_update: NotRequired[CustomerSafeReport]
    failure: NotRequired[SafeWorkflowFailure]
```

`ExtractionResult` and `ExtractionCallRecord` exist, and RF-303/304 now implement
preliminary `DiagnosisDraft`, `CustomerSafeReport`, `SafeWorkflowFailure`, and
`ClarificationTurn` contracts. RF-306 adds the immutable `ProposedAction` contract
and its optional state field. RF-307 adds `ApprovalDecision` and its optional
state field, plus a separate stage requiring a saved proposal.
RF-308 adds `ToolExecutionResult` and the simulated ticket-ID fields. Confirmation
and evidence result types still name future contracts to define when their stages
are implemented.
Clarification turns identify round, questions, and any answers. Failures record
stage and safe reason, excluding SDK messages and report text. Confirmation
records actor, time, and exact extraction version. Evidence pins source version
and location. Approval binds to immutable action arguments; tool code must
separately prevent duplicate effects.

## Stage ownership

| Stage | Durable value or record reference | Recompute or reload | Why |
| --- | --- | --- | --- |
| Start from report | `workflow_run_id`, `issue_report_id` | Original report and current access scope from the database | A run can resume without storing report text or trusting old permissions. |
| Classify and extract | Validated `extraction`, `extraction_call` | Prompts and severity/clarification display | Resume preserves the proposal and prompt version; extraction includes service/severity. |
| Evaluate context | Typed model evaluations used downstream, when introduced | Deterministic checks such as `decide_clarification(extraction)` | Derive routing from saved facts; save model judgments so resume preserves them. |
| Ask and answer clarification | Ordered `clarification_turns` with questions and accepted answers | Round count and pending questions | Preserve questions/answers through interruption and enforce the round limit. |
| Customer confirmation | Typed `customer_confirmation` | Confirmation display from the decision and saved extraction | The customer's decision must be attributable and cannot be inferred from a node name. |
| Retrieve evidence | Typed `evidence` snapshots after authorized retrieval | Search query and presentation formatting | Resume and diagnosis cite the same selected source versions and locations. |
| Diagnose | Typed `diagnosis` draft | Presentation formatting | A generated assessment should not change silently on resume. |
| Propose action | Immutable typed `proposed_action` | Display of exact arguments and version | Approval must bind to that exact proposal. |
| Approve or reject | Typed `approval` decision | Decision display | Recheck that the decision applies to the current action version before execution. |
| Execute tool | Typed `tool_execution`; `support_ticket_id` after successful creation | Execution display | Resume must not duplicate a consequential action; the tool boundary enforces idempotency. |
| Report outcome | Typed `customer_update` | Presentation formatting | Internal diagnosis and customer-visible status stay separate. |
| Handle failure | Typed, safe `failure` or a durable failure record | Human-readable message from its reason code | Resume and inspection need the failure stage without exposing provider internals. |

## Boundaries for later tickets

- RF-302 decides transitions, terminal outcomes, and which failure paths resume.
- RF-303 implements the minimal typed graph using the subset of fields its nodes
  need. The [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
  accepts a Python `TypedDict` state schema; node updates are applied to its
  fields. Diagnosis and report results live in checkpoint state until separate
  records are introduced.
- RF-304 implements two answered rounds and explicit incomplete continuation
  with in-memory pauses; see [workflow clarification](workflow-clarification.md).
- RF-305 selects and tests durable checkpoint storage across a process restart,
  including serialization of the typed state and restoration of the same run.
- RF-306 defines immutable proposed actions; see [proposed actions](proposed-actions.md).
- RF-307 defines typed exact-proposal decisions; see [action approval](action-approval.md).
- RF-308 defines simulated execution results; see [simulated tool](simulated-ticket-tool.md).
- RF-310 adds a typed timeline list with an append reducer, saved alongside
  each transition in checkpoint state; see [execution timeline](execution-timeline.md).
  Other future contracts above remain placeholders until reviewed.
