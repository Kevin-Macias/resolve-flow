# Proposed actions (RF-306)

Kevin approved an immutable `create_ticket` proposal with typed arguments,
explanation, expected effect, risk level/reason, and application-assigned identity.
The contracts live in `apps/api/src/api/workflow/actions.py`.
Kevin approved the implementation and revision behavior in the RF-306 PAIR review.

## Contract

| Field | Meaning |
| --- | --- |
| `action_id` | Application-generated UUID identifying the logical proposal |
| `version` | Positive integer, starting at 1 and increasing for revisions |
| `idempotency_key` | Application-generated UUID saved once for this version |
| `tool` | Only `create_ticket` is accepted |
| `arguments` | Report ID, title, description, nullable service code and tentative severity |
| `explanation` | Why the action is proposed |
| `expected_effect` | What the tool is expected to change |
| `risk` | `low`, `medium`, or `high`, with a nonempty written reason |

Title, description, explanation, effect, and risk reason must contain nonempty
text. Nullable service/severity fields remain required, with `null` explicitly
representing unknown classification. Unknown fields are rejected. Account scope,
permissions, approver, and assignment are not accepted as ticket arguments.

Risk describes the proposed action; it is separate from incident severity. These
labels have no automatic authorization or execution policy in RF-306. Later
approval and tool code must still review the proposal and enforce access.

## Creating and revising

```python
action = propose_create_ticket(
    CreateTicketArguments(
        issue_report_id=issue_report_id,
        title="Pending payments",
        description="Customer reports two payments still pending.",
        service_code="payments",
        severity=None,
    ),
    explanation="Support should investigate the reported payment outcome.",
    expected_effect="Create one internal support ticket linked to this report.",
    risk=ActionRisk(level=RiskLevel.LOW, reason="Simulated ticket creation only."),
)
```

`propose_create_ticket` assigns ID, version 1, and idempotency key in application
code. The Pydantic contracts are frozen, including nested arguments and risk.
`revise_create_ticket` returns a new immutable snapshot with the same action ID,
version + 1, and a new key. Revisions stay attached to the same issue report.
Retrying or resuming uses the saved snapshot, without calling either factory
again. Persist the proposal before displaying it for review.

`fingerprint()` computes SHA-256 over canonical JSON containing the complete
normalized snapshot, including arguments, rationale, risk, identity, and version.
It is stable across serialization and JSON key order. Any changed review content
changes the fingerprint. It is a comparison value, not a signature or permission.
RF-307 binds approval to the saved proposal and validates that it is still current.

Frozen models prevent ordinary assignment, but Pydantic's `model_copy(update=...)`
can create unvalidated objects. The factories revalidate nested inputs and the
previous proposal; application boundaries must validate again before use.
The raw `ProposedAction` constructor is an internal serialization contract, not
permission for a model or customer to assign authoritative IDs or approval.

## Workflow and scope

`WorkflowState.proposed_action` can hold the saved typed proposal. The checkpoint
serializer permits these exact action types and restores the arguments, risk,
version, idempotency key, and fingerprint. Existing checkpoints can omit the new
optional field.

RF-306 defines contracts and factories. The current intake graph does not generate or
execute a proposed action, and does not infer approval from a stored proposal.
RF-307 now provides a separate [approval stage](action-approval.md);
RF-308 now connects an optional [simulated tool](simulated-ticket-tool.md); RF-309/703
verify execution and idempotency behavior. A UUID key alone does not prevent
duplicate effects.

## Review cases

- Unknown impact is accepted as `severity=None`; ticket creation does not invent
  impact or elevate tentative classification to a verified finding.
- Changing severity produces a new version and key while preserving the old
  snapshot; old approval must not authorize that revision.
- Retrying a saved proposal preserves its ID, version, key, and fingerprint.
- Changing rationale also changes the fingerprint, even with unchanged arguments.
- Blank text, unsupported tools/risk levels, extra scope fields, and zero or
  boolean versions are rejected.

Offline tests in `tests/workflow/test_actions.py` verify these contracts,
immutable nested values, revisions, and typed checkpoint round trips.

Verification on 2026-09-26: `pnpm check` passed formatting, lint, generated client
drift checks, all type checks, and all 169 tests with PostgreSQL available.
