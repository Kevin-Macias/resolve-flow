# Execution timeline (RF-310)

Kevin chose a typed event list in graph state, persisted by the existing
PostgreSQL checkpointer. Events use a closed metadata contract rather than free
text. The implementation awaits the PAIR review.

## Event contract

`ExecutionEvent` in `workflow/timeline.py` contains:

- `event_id`: deterministic UUID derived from the run, stage, event type, and
  transition identity, such as clarification pause ID or proposal fingerprint.
- `workflow_run_id` and `stage`: bind the event to intake or approval.
- `sequence`: consecutive position within that stage, starting at 1.
- `occurred_at`: server-generated UTC timestamp, retained after checkpoint restore.
- `event_type`: stable enum for later display labels and localization.
- `metadata`: frozen `EventMetadata` with only approved typed fields.

Metadata may hold clarification counts/reason enums, attempt counts, typed
extraction/provider failures, action ID/version/fingerprint, trusted actor ID,
simulated ticket ID, and an incomplete or unknown-outcome flag. It cannot hold
report text, questions, answers, prompts, tool arguments, raw output, free-form
messages, or exceptions. Unknown fields are rejected. These are internal events:
IDs and action bindings still require authorized access and a customer-safe
projection before any public exposure.

## Recording transitions

Nodes return a `timeline` delta with their state update. The `append_events`
reducer appends events, checks contiguous sequence and run/stage ownership, and
rejects attempts to change an existing event. Replaying an identical event
preserves its saved timestamp. `transition_event` does not emit an already
committed transition again.

The checkpoint stores events and the associated state update together. There
is no separate event-table write to reconcile. Use `durability="sync"` with
PostgreSQL to save each completed graph step before proceeding.

The intake graph records:

```text
workflow_started
  -> extraction_succeeded -> clarification_evaluated
       -> clarification_requested -> clarification_answered -> extract again
       -> continued_incomplete -> diagnosis_prepared -> report_ready
       -> diagnosis_prepared -> report_ready
  -> extraction_failed -> report_ready
```

The start node records workflow initialization. Clarification-request events are
saved in the preparation node before the interrupt. Answer and explicit
incomplete-continuation events are saved only after a valid reply. Polling or
invalid replies do not add events. Provider retries remain inside the extraction
service; the outcome event records the attempt count, not individual SDK calls.

The approval graph records:

```text
approval_requested
  -> action_rejected
  -> action_approved -> tool_succeeded | tool_failed
```

A preparation node saves the proposal binding before approval pauses. The exact
accepted decision records its trusted actor. Tool failure records an unknown
outcome; it never claims that no effect happened. Without an injected tool,
approval ends at `action_approved`, matching the awaiting-execution state.

Use the guarded `ApprovalRunner` from RF-309 for submissions. Duplicate and
concurrent requests reuse the saved state and timeline. Unauthorized requests
and stale transport input do not record an accepted decision or tool outcome.
An authorization exception before dispatch may leave the last event as
`action_approved`. Request-denial logging is separate RF-704 work.

## Reading the run

The existing graphs have separate checkpoint threads: `<run UUID>` for intake
and `<run UUID>:approval` for approval. Each stream has its own sequence.
`combined_timeline(intake_events, approval_events)` returns an immutable view
with intake first, then approval, and rejects mixed runs or stage ownership.
This follows product flow rather than relying on clocks across processes.
A future UI can number this combined view for display while using event IDs for
reconnect and deduplication.

```python
intake = await graph.aget_state(workflow_config(run_id))
approval = await stage.aget_state(approval_config(run_id))
events = combined_timeline(
    intake.values.get("timeline", []),
    approval.values.get("timeline", []),
)
```

Reads must be scoped to an authenticated actor and report. This ticket adds no
HTTP endpoint, SSE transport, or timeline UI; those belong to RF-503/504.
The other checkpoint fields still contain internal customer content even though
the timeline is sanitized. Never expose the complete graph state to customers.

## Limits and verification

Events describe committed graph transitions, not every attempted instruction.
An unfinished node may leave no outcome event; a crash can occur after a tool
acts and before its result is checkpointed. The RF-309 runner does not retry
that saved approval automatically. Real effect reconciliation remains RF-703.

Start a new execution with a fresh run ID; resume an existing run with its saved
pause. Do not restart a completed run by submitting its original input again.
Existing checkpoints are not retroactively given events for past transitions.
The append rule is an application invariant, not a database audit ledger that
resists direct privileged checkpoint edits. Retention and archival are separate
work.

Tests cover ordered clear/failure/clarification paths, the two-round limit,
invalid input and polling, forbidden metadata, immutable contracts, changed
and misordered events, and typed serialization. PostgreSQL workers verify exact
IDs, timestamps, sequence, and metadata after restart; concurrent/duplicate
approval and failed-tool replay preserve the exact saved event list. No live
model calls or external ticket writes are used.

Verification on 2026-09-26: `pnpm check` passed formatting, lint, generated-client
drift checks, all type checks, and all 227 tests with PostgreSQL available.
