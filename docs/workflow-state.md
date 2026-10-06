# Workflow state design (RF-301)

One workflow run starts from an existing `IssueReport`. The run keeps its report
ID throughout intake, clarification, internal review, approval, and reporting.
`support_ticket_id` appears only if the approved create-ticket action succeeds.
A status lookup that does not create a report is a separate use case. Kevin
approved this design in the RF-301 PAIR review.

## State rule

Keep values that must survive a pause or restart, including human answers and
model proposals that must not silently change on resume. Keep a reference to a
durable application record when that record already owns the data. Reload the
original report by `issue_report_id`; its description is not copied into the
checkpoint. Derive presentation text, routing flags, and prompt formatting when
needed. A checkpoint is workflow memory, not proof of authorization: every
database read and tool action must check the current actor or trusted execution
context's access policy.

The full shape below is an approved design sketch. RF-303 implements its minimal
subset in `apps/api/src/api/workflow/state.py`, with a derived clarification
decision and preliminary diagnosis; later-stage contracts remain planned.
RF-304 adds ordered `clarification_turns`, a saved `pending_clarification` with
questions and a stable pause ID, and `continued_incomplete`. Its in-memory
checkpointer permits pauses within one process, without restart durability.
Keep typed results in checkpoint state until separate application records own
them. When those records are introduced, their IDs can replace the corresponding
snapshots through an explicit state migration. Restoring across process restarts
requires the persistent checkpointer added and tested in RF-305; RF-301 does not
implement storage. RF-305 now provides explicitly injected
[PostgreSQL checkpoints](workflow-checkpoints.md) with tested typed restoration.

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
A clarification turn must identify its round, question, and answer (if any).
A safe failure must
identify the stage and stable reason without SDK messages or report text.
Customer confirmation must identify the actor, time, and exact extraction
version confirmed. Evidence must pin the source version and location used.
Action and approval snapshots must bind the decision to immutable arguments;
checkpoint restoration alone does not guarantee idempotent tool execution.

## Stage ownership

| Stage | Durable value or record reference | Recompute or reload | Why |
| --- | --- | --- | --- |
| Start from report | `workflow_run_id`, `issue_report_id` | Original report and current access scope from the database | A run can resume without storing report text or trusting old permissions. |
| Classify and extract | Validated `extraction`, `extraction_call` metadata | Prompt formatting and severity/clarification displays | Resume uses the same model proposal and prompt version; service and severity already live inside `extraction`. |
| Evaluate context | Any model-produced evaluation that later nodes rely on must be saved as a typed result when introduced | Deterministic checks such as `decide_clarification(extraction)` | Routing may be recalculated from saved facts; nondeterministic judgments cannot safely be rerun as if unchanged. |
| Ask and answer clarification | Ordered `clarification_turns`, including unanswered questions and accepted answers | Number of rounds and current pending questions from the turns | Questions and customer answers survive interruption; the round limit can be checked from history. |
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
