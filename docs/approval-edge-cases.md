# Approval edge cases (RF-309)

Kevin approved these expectations: stale or changed proposals cannot execute;
the first accepted decision wins; duplicate requests return the saved outcome;
concurrent submissions for one run are serialized; tool failures save a safe
error without automatic retry. Kevin approved the implementation and important
cases in the RF-309 PAIR review.

## Guarded submission

Use `ApprovalRunner.submit(run_id, reply)` to submit an approval or rejection.
The runner locks the run before reading current state, checks its identity,
checks current support access to its report, and validates the reply against
the saved proposal. An invalid or stale reply raises `ValueError` without
advancing the graph. Unlike a direct graph resume, it does not create another
interrupt for transport validation errors.

When a decision is already saved, the runner returns the saved state. This
includes a later opposite choice: it cannot overwrite the first decision.
Access and proposal binding are checked even for duplicate requests. A rejected
action stays rejected and never calls the tool. Changed arguments invalidate an
old reply even when the action ID and version were reused.

`MemoryRunLocks` is for offline tests: share one instance between runners using
one checkpoint store. It coordinates tasks in one process only and retains locks
for its lifetime. With PostgreSQL checkpoints, use `PostgresRunLocks` with the
same database URL and checkpoint schema as its namespace in every worker. Each
submission holds a session advisory lock on a dedicated connection until the
graph's synchronous checkpoint writes finish. Connection closure releases the
lock on success, exception, cancellation, or process exit. Different runs use
different lock keys.

Initialization and proposal revisions are trusted orchestration operations.
They must use the same run lock when concurrent with submissions. Do not revise
a decided run in place: a saved decision that no longer matches the proposal is
rejected, and a new review needs a separate approval run. Before a decision, a
trusted proposal revision must establish a fresh review interrupt before any
submission can be accepted. Do not expose
raw `ainvoke`, `aupdate_state`, checkpoint history, or resume commands to clients.
The runner returns internal state; a future API must project customer-safe data
and authenticate before displaying internal checkpoint or interrupt information.

## Failure and restart

Argument and authorization errors happen before dispatch and propagate without
calling the adapter. Adapter exceptions, including invalid returned data, become
a sanitized `ToolCallError`. The graph saves `ToolExecutionFailure` containing
the action binding, idempotency key, reason `tool_failed`, and outcome `unknown`.
It saves no success result or support-ticket ID. The safe message says ticket
creation could not be confirmed and support review is required; exception text
is not saved.

A tool could have acted before raising. An unknown outcome must not be described
as proof that no ticket exists. No tool retry is automatic. Duplicate submission
returns the saved failure, including after restart.

A saved approval with no execution result also returns as-is. This can happen
when execution access is revoked, a process dies, or a checkpoint write fails.
A duplicate approval does not resume unfinished execution. Reconciliation and
real effect idempotency belong to RF-703. The lock is request coordination, not
an atomic transaction combining checkpoints with external effects. The current
tool remains a pure deterministic simulation with no persisted ticket write.

## Review cases

- Stale ID, version, or fingerprint: no decision or tool call.
- Changed arguments: old reply fails; current reply executes the current proposal.
- Rejection followed by approval: saved rejection, zero tool calls.
- Approval followed by duplicates or rejection: same saved result, one tool call.
- Concurrent approvals or approve/reject: first accepted decision preserved.
- Completed execution after process restart: duplicate returns the exact result.
- Tool raises before or after simulated creation: unknown outcome, no success ID,
  no retry on repeated submission or restart.
- Revoked access: cannot submit or retrieve an outcome through the runner.
- Approval saved before execution access fails: duplicate does not retry execution.

Tests live in `tests/workflow/test_approval_runner.py` and the PostgreSQL restart
suite in `tests/workflow/test_checkpoints.py`. Concurrent process tests use two
independent graph/checkpointer/lock connections against the same run.

Verification on 2026-09-26: `pnpm check` passed formatting, lint, generated-client
drift checks, all type checks, and all 211 tests with PostgreSQL available.
No live model call or external ticket write was made.
