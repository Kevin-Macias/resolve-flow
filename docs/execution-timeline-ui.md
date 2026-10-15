# Execution timeline UI (RF-504)

Status: DONE. Database-backed integration verification passed on 2026-10-12.
RF-511 and RF-513 are DONE. The broader hands-on platform review
remains scheduled at the [platform checkpoint](roadmap.md#platform-review-checkpoints).

## Goal

Show an authorized support engineer the saved transitions for one workflow run.
Use the existing RF-310 events; never infer history from chat, customer-safe SSE
snapshots, or the browser's connection history.

## Existing contract

`apps/api/src/api/workflow/timeline.py` supplies immutable execution events and
`combined_timeline`. Intake precedes approval; sequence is local to each stage.
Keep that order even if timestamps differ across processes. Use `event_id` for
React keys, and show the saved timezone-aware `occurred_at` timestamp rather than
browser receipt time. Repeated reads must not append duplicate display entries.

The approved workspace design places the timeline below actions in the internal
support workspace. These events include internal action/actor identifiers and
are not a customer projection. Do not attach this component to the customer
report detail page or send these events through RF-503's customer-only stream.

## Component behavior

The component receives one run's authorized events and loading/error/stale
state. Render an ordered list with stage, readable transition name, saved
timestamp, and supported metadata. Preserve intake/approval order and each
stage's sequence, independently of clock time.

Distinguish an empty saved history from loading, failed reads, and analysis not
started. Retain a previously authorized view with a stale notice during temporary
connection failure; remove it on access loss or identity/run changes. A refresh
reads history; it must not start, resume, approve, reject, or retry execution.

Describe important outcomes precisely:

- `report_ready` means the intake report was prepared, not a support ticket was
  created or the issue resolved.
- `continued_incomplete` keeps the incomplete-context label visible.
- `action_approved` records a decision, not tool success.
- `tool_succeeded` with simulated outcome is clearly labeled simulated.
- `tool_failed` with unknown outcome says the effect is unknown, not that no
  effect occurred. Do not offer a tool retry from the timeline.

Use the existing Tailwind theme and shared controls. Free-form raw metadata,
customer text, prompts, arguments, and exception messages are not display data.

## Browser integration

- `/support`: enter a report UUID to open its timeline.
- `/support/reports/$reportId`: read the RF-513 endpoint, show the saved run ID,
  provider/simulation label, pending-operation notice, and intake history.

There is no support queue endpoint yet, so the entry accepts a known report ID.
The page does not use customer report endpoints or claim to verify archival.
A 404 cannot distinguish an inaccessible report from a report without a run;
it shows unavailable, never "analysis not started."

The shared demo session boundary gives customer and support routes separate
in-memory identities and QueryClients. Switching experiences ends the old
session, cancels reads, clears its cache, and invalidates late mutation callbacks.
The API establishes the role and account grants; navigation grants no access.
See [support run reads](support-run-reads.md) for authorization and configuration.

`features/execution-timeline/api.ts` uses the generated client and forwards query
cancellation to the support GET. Shared Zod schemas validate the closed response,
metadata, timestamps, report/run binding, unique event IDs, contiguous intake
sequence, and simulation label before caching. Invalid responses use a fixed
safe message and replace previously cached history.

Queries are scoped to identity and report, with no previous-report placeholder.
Refresh replaces the saved array instead of appending it. Temporary failures
retain previously authorized history with a stale notice. HTTP 401/403/404
removes that history and run details; session/report changes also remove them.
Read retries are disabled; refresh performs only the authorized GET.

The reusable component can render intake followed by approval events in their
supplied order. The current production endpoint exposes intake only. Approval
outcomes are covered by serialized contract fixtures and await a trusted backend
binding before live display. The page adds no workflow mutation controls.

## Review walkthrough

Use the configured, migrated PostgreSQL database and checkpoint setup from
[customer intake runs](customer-intake-runs.md). Create a customer report and
start intake through its documented endpoint; record the report UUID. Configure
an existing support user's demo token and per-user account grants as described
in [support run reads](support-run-reads.md), then restart the API as needed.

1. Open `/support`, enter the support token, and open that report ID. Confirm
   the saved run, simulation label, event order, and timestamps.
2. Refresh twice: rows must not duplicate and workflow execution must not resume.
3. Submit clarification through the customer endpoint, then refresh support
   history and verify the newly saved transitions.
4. Interrupt API access and refresh: keep the old history with a stale notice.
   Restore access and refresh to replace it with current saved history.
5. Revoke the support account grant and restart the API, then refresh: hide the
   events and run details. Try another report or support identity and confirm
   the previous history is not displayed while its read is pending.
6. Switch to customer reports: require a separate customer token and show no
   internal history. Check the support page at desktop and mobile widths.

## Verification and remaining work

On 2026-10-12, root `pnpm check` passed Python formatting/lint, generated-client
checks, strict Python/TypeScript checks, the production web build, all 518 backend
tests, and 85 frontend tests against a task-owned disposable PostgreSQL/pgvector
database. No tests were skipped. The tokenizer vocabulary was cached for offline
checks; no live model calls ran.

The frontend suite uses responses serialized by the Python `SupportRun` and
`ExecutionEvent` models. It covers stage order despite out-of-order clocks,
saved timestamps, loading/empty/error/stale states, safe outcome labels,
repeat reads, invalid payloads/bindings, access loss, report changes, cancellation,
late responses after identity changes, and separate customer/support sessions.
Approval events in fixtures do not claim live approval integration.

Production Chromium verification used intercepted HTTP fixture responses. It
checked hydration, desktop/mobile overflow, access-loss removal, separate
customer sessions, and absence of runtime exceptions. These checks do not
verify persisted HTTP integration.

After Docker became available, the database-backed walkthrough passed using
real HTTP requests, the production web build, Chromium, migrated PostgreSQL,
and durable checkpoints. No browser responses were intercepted in this run.

- Customer start saved four intake events; clarification saved nine. Support
  refresh displayed the new history with the exact saved order and timestamps.
- Repeated refreshes did not duplicate rows. Database digests of run/operation
  records and checkpoint tables were unchanged by those support reads.
- Page reload required token entry and restored saved history. An actual API
  outage kept history with a stale notice; restarting the API restored the same
  events and cleared that notice after refresh.
- Authorized support still read an archived report's history while customer
  reads returned 404. Revoking account grants removed cached events and run
  details; restoring grants allowed a fresh read.
- A foreign report and another ungranted support identity returned unavailable
  without displaying previous history. Customer navigation required its own
  session, and the support token was absent from browser storage.
- Desktop and mobile rendering had no overflow, JavaScript exceptions, or failed
  production assets. The browser made 12 timeline GETs and no workflow writes.

RF-504 is DONE and RF-505 is NEXT. The task-owned database container and local
services were removed after verification; no project database changes were made.
The broader hands-on platform checkpoint remains pending.
