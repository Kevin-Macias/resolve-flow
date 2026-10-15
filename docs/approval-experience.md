# Approval experience (RF-507)

Status: approved by Kevin in the RF-507 PAIR review on 2026-10-12.
RF-508 now implements this design with the approved
[support simulation HTTP integration](support-approval-controls.md). Verification
is complete; Kevin accepted final PAIR implementation review on 2026-10-13.

Support reviews the complete saved action in the report workspace, below
Diagnosis, as placed in the [workspace design](workspace-information-architecture.md).
The learning objective is to distinguish a proposal, an accepted decision, and
an execution result. Each answers a different question: what might happen, what
support authorized, and what the application can confirm happened.

## Review card

Keep the action and its consequences visible beside the decision controls.
Use a single column on mobile. The example below is illustrative data, not a
live proposal or a verified diagnosis.

```text
Proposed action                         Version 1
Create support ticket (create_ticket)
Simulation: no persisted support ticket or external write

Exact arguments
  Report ID:    <full issue report UUID>
  Title:        Investigate missing issue report
  Description: Customer cannot find a previously submitted report.
  Service:     Not specified (null)
  Severity:    Unknown (null)

Why this action
  Support should investigate the reported visibility problem.

Expected effect
  Simulate creating one internal ticket linked to this report.

Action risk: Low
  This adapter only simulates ticket creation.

Reversibility
  Simulation has no ticket write to undo. An accepted decision remains
  recorded; this screen does not offer undo or delete.

[Review approval]    [Review rejection]
```

Show all five argument fields from `CreateTicketArguments`, including full
report ID and complete description. Wrap long text and UUIDs; do not truncate
values needed for review. Keep null values explicit without inventing service
or severity. Label severity as tentative when supplied. Action risk is separate
from incident severity and includes the saved risk reason.

Use `ProposedAction.explanation`, `expected_effect`, and `risk` directly. Render
proposal text as text, without executing embedded HTML or treating it as an
instruction. The proposal remains read-only. Changing its contents requires a
new reviewed version through trusted orchestration; the UI cannot alter arguments
inside an approval request.

Reversibility is not a field in the current proposal contract. For the existing
simulated `create_ticket` adapter, use application-owned copy describing its
actual behavior, as above. Do not derive reversibility from model prose or a low
risk label. A real adapter requires reviewed effect and reversibility information
before enabling its approval controls.

Keep action ID, fingerprint, and idempotency key in an optional technical details
section. Version and the exact arguments remain visible without expanding it.
The saved fingerprint binds the full proposal, including its reason and risk.

## Decision interaction

Use an inline confirmation step for both decisions. It keeps the proposal
visible while making the choice explicit. Kevin approved these choices:

- **Review approval** opens: “Approve version 1 and allow the simulated ticket
  action?” Buttons: **Approve version 1**, **Keep reviewing**.
- **Review rejection** opens: “Reject version 1? This action will not execute.”
  Buttons: **Reject version 1**, **Keep reviewing**.
- Cancel returns to the unchanged proposal and sends no request. Do not require
  typed confirmation or a checkbox for this simulated action.
- Do not collect a rejection reason in this version: the existing decision
  contract has no reason field. Rejection ends this action path; it does not
  automatically generate another proposal.

Only one confirmation can be open. Neither final decision button receives
automatic focus. Move focus to the confirmation heading and return it to the
trigger on cancellation. Use text labels, visible focus, and an announced status
for submission and saved outcomes.

Pin the confirmation to the displayed action ID, version, and fingerprint.
If any changes before submission, close it, show “The proposal changed. Review
the current version before deciding,” and require a fresh review. The server
must still check the binding at submission because another reviewer may act
between the latest read and the click.

The decision body contains only `action_id`, `version`, `fingerprint`, and
`decision`. The authenticated backend supplies actor and decision time. Run/report
binding and current support account access belong to the application endpoint;
client fields cannot establish authorization. Use the guarded
[approval runner](approval-edge-cases.md), rather than raw graph resume.

## Saved outcomes and interrupted requests

These are display states, not proposed backend enum names.

| Saved situation | Display and available interaction |
| --- | --- |
| Loading | Show loading; decision controls unavailable |
| No proposal | “No action is currently proposed”; no decision controls |
| Awaiting decision | Full review card and confirmation controls for authorized support |
| Submitting | Disable both choices; show “Submitting decision”; no optimistic approval or execution result |
| Proposal changed | Close confirmation, block the obsolete version, and fetch current saved state for a fresh review |
| Decision accepted by another reviewer | Show the saved decision and its outcome, even if different from this reviewer's attempted choice |
| Approved, no execution result | Show “Approved; execution is not confirmed” with the saved decision receipt; refresh may read state, but there is no execute/retry button |
| Rejected | Show rejection receipt and “This action did not execute”; remove both decision controls |
| Simulated success | Show saved simulated ticket ID and status with “Simulation; no persisted support ticket was created” |
| Execution failure or unknown outcome | Preserve the approval receipt; show that creation could not be confirmed and support review is required; no blind retry |
| Network error or uncertain submission | Show “Your decision may have been saved. Refresh before deciding again”; disable decisions until a successful saved-state read |
| Disconnected or reconnecting | Keep the last saved proposal with a stale notice, close confirmation, and reconcile current state before allowing a fresh review |
| Access lost | Remove protected proposal, decision, and result data; show a safe unavailable state |

The receipt shows the accepted decision, proposal version, server actor identifier,
and server timestamp. Do not invent a display name or infer the decision from
which button was clicked. Keep execution outcome below the receipt so approval
is never presented as proof that a ticket exists.

The runner's first accepted decision wins. A duplicate or opposite later choice
returns the saved outcome after access/binding checks. A duplicate approval with
unfinished execution does not restart it. Read-only refresh and reconnect must
also never trigger execution. Effect reconciliation remains RF-703 work.

## Integration needed before RF-508

Existing foundations are [immutable proposals](proposed-actions.md),
[approval contracts](action-approval.md), the guarded runner, and the simulated
tool. They are reusable Python stages, separate from customer intake.
RF-513 currently exposes saved intake timelines, not proposal/decision endpoints.

Before live controls, Kevin must review support proposal creation/orchestration,
authorized reads of proposal/decision/execution state, and a decision operation
bound to the correct report, workflow run, and approval stage. Define transport
errors and freshness/reconnect semantics there. Do not reuse customer intake
recovery for approval execution or expose internal checkpoints to the browser.

## Design review cases

Review this design with: an ordinary approval; a rejection; null classification;
a long description on mobile; proposal revision while confirmation is open;
another reviewer deciding first; a lost response after acceptance; an approval
without an execution result; an unknown execution outcome; and revoked access.

Kevin accepted the layout, inline confirmations for both decisions, outcome
wording, and reversibility treatment on 2026-10-12. Documentation links and
whitespace checks passed. RF-507 is DONE. RF-508's verification and accepted
final PAIR review are recorded in [support approval controls](support-approval-controls.md).
The RF-507 design itself changed no runtime code and made no model or tool call.
