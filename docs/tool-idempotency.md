# Durable simulated execution (RF-703)

Kevin approved this PAIR design on 2026-10-15: save an operation before dispatch,
let the simulated destination remember its effect, and recover with the same key
after a crash. He accepted final PAIR implementation review on 2026-10-18.

This applies to the support HTTP approval path. The reusable graph still supports
the pure in-memory fake for offline tests. No real support ticket or external
write is introduced.

## What each part remembers

| Record | Owner | Contents | Commit boundary |
| --- | --- | --- | --- |
| `execution_operations` | Application | Run, key, exact proposal, approval, fingerprint, nullable result | Intent before dispatch; result after the destination replies |
| `simulated_ticket_effects` | Simulated destination | Key, fingerprint, simulated ticket ID, full execution receipt | Effect and receipt in one row and transaction |
| Approval checkpoint | Workflow | Decision, outcome, customer-safe status, ordered events | Separate from the operation and destination commits |

A null application result means completion has not been recorded locally. The
destination may already have committed its effect. Both tables use PostgreSQL in
this simulation, but their transactions are separate from each other and the
checkpoint. The destination has no foreign key to the application's ledger.
Records survive restarts and have no automatic expiry or deletion API. Deleting
receipts would remove their replay protection.

## Execution

1. Recheck support access and report/intake observations; validate exact approval.
2. Commit the application intent under the proposal's saved idempotency key.
   Unique constraints bind one operation to the run. Existing intent must match
   the proposal and saved approval exactly.
3. Ask the destination to execute the same proposal and key. A transaction-level
   advisory lock serializes requests for that key.
4. Return an existing matching receipt unchanged, including its original actor.
   Reject the same key with a different proposal. If no receipt exists, recheck
   current access/freshness, generate the fake result, and commit its effect and
   receipt together.
5. Save the application result, then save the workflow outcome and success event.

The pure fake's Python `calls` list is test instrumentation. The committed
`simulated_ticket_effects` row is the durable simulated effect. A real remote
write cannot join or be rolled back by this local transaction.

See [`support/execution.py`](../apps/api/src/api/support/execution.py),
[`action_models.py`](../apps/api/src/api/support/action_models.py), and
[`actions.py`](../apps/api/src/api/support/actions.py).

## Explicit recovery

`POST /support/issue-reports/{report_id}/runs/{run_id}/recover-execution`
returns the existing `SupportAction` projection and uses the support endpoints'
bearer-token and account-grant rules. Its body identifies the saved approval:

```json
{
  "action_id": "<saved action UUID>",
  "version": 1,
  "fingerprint": "<saved proposal fingerprint>",
  "decision": "approve"
}
```

The body cannot approve an undecided or rejected action. Recovery takes the
report lock before the run lock. It requires current authorized support access,
an active eligible report, unchanged observations, the registered proposal,
matching checkpoint approval, and matching durable intent. Changed/archived input
returns 409; access loss uses the existing 401/403/404 responses.

Recovery uses the saved application result, or asks the destination again with
the original key. An existing destination receipt is returned unchanged. If its
transaction never committed, the destination can safely produce the effect once.
Recovery then saves the result and updates the checkpoint as the execution node.
An earlier failure event stays in history; its current failure projection is
cleared when execution is confirmed. Success events retain stable IDs.
Recovery includes the observed approval and event prefix because LangGraph can
save node writes before folding them into the main checkpoint. The timeline
reducer deduplicates events already present in that checkpoint.

GETs and repeated decision submissions do not recover execution. The command is
available through the API and generated client. The support screen continues to
show saved outcomes and does not initiate recovery.

An unknown execution without an operation record stays manual and returns 409.
This includes legacy attempts and an interruption before intent reservation.
Recovery cannot infer a safe destination contract for those attempts. Current
policy also blocks recovery after archival or observation changes, even if an
old receipt may exist. Read-only reconciliation for those cases would require
a separate policy decision.

## Crash windows

| Process ends | Durable state | Explicit recovery |
| --- | --- | --- |
| Before intent commits | Approval may exist; no operation | Manual review; no dispatch |
| After intent, before effect | Pending operation; no receipt | Execute the same approved simulation once |
| During destination transaction | Pending operation; uncommitted effect rolls back | Execute once after rollback |
| After effect commit, before application result | Pending operation and destination receipt | Reuse destination receipt |
| After application result, before checkpoint | Completed operation and receipt | Restore workflow from saved result |
| After checkpoint | All outcomes saved | Return saved outcome |

Approval fingerprints establish what was approved. Authorization establishes who
may act. Run locks coordinate submissions. Destination receipts prevent duplicate
simulated effects after restart. Each addresses a different part of safety.

An external integration needs its own reviewed contract for atomic key/effect
storage, argument mismatch, concurrency, lookup/replay behavior, and key retention.
A local ledger alone cannot make a remote write safe. If the destination cannot
resolve uncertainty safely, recovery must remain manual. Recovery never changes
arguments, creates a replacement key, revises the proposal, or changes a decision.

## Verification and review

Migration [`0006`](../apps/api/migrations/versions/0006_durable_simulation.py) creates
the tables and cleanly rolls back. Apply it through the normal Alembic workflow
before using the support execution endpoints. Checks use disposable PostgreSQL;
the project database has not been migrated.

[`test_execution_recovery.py`](../apps/api/tests/intake/test_execution_recovery.py)
terminates real interpreter processes before/during the effect, after the effect
commit, and after the application result commit. A separate interpreter recovers
the operation. It checks one effect, the original receipt, and one success event.
Other cases cover explicit recovery, concurrent replay, key/run binding, missing
historical intent, and existing access/freshness/approval rules. The support HTTP
access matrix includes recovery. Exact check results are in the roadmap.
One regression freezes the checkpointer at its durable-node-write boundary to
verify that recovery retains approval and contiguous events in the main snapshot.

Kevin accepted the crash-window behavior in final PAIR review on 2026-10-18.
The destination receipt survives independently of the workflow checkpoint.
[Invitation authentication](authentication-and-access.md) supplies current identity
and grants; neither saved approval nor a receipt replaces those access checks.
