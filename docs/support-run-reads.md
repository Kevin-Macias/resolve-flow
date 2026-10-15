# Support run and timeline reads (RF-513)

Kevin approved the authorization and response contract on 2026-10-09.
Implementation and final PAIR review results are recorded below.

## Approved contract

`GET /support/issue-reports/{report_id}/intake-run` is a read-only endpoint that
returns the report's saved intake run and ordered RF-310 events. It reads stored
data directly, independently of intake provider configuration. The report ID
selects the run; callers cannot supply checkpoint/thread IDs or workflow state.

Access requires a bearer token for a current database user with the support role.
`DEMO_SUPPORT_ACCOUNT_IDS` maps support user UUIDs to permitted customer account
UUIDs, for example:

```json
{"00000000-0000-0000-0000-000000000001": ["00000000-0000-0000-0000-000000000002"]}
```

The IDs must refer to actual local records. These grants simulate access for the
demo. Missing grants or malformed configuration deny access.

Check current credentials, role, grants, and report/run/account ownership before
reading the checkpoint and again before returning the response. Authorized
support can read archived reports' timelines; customer reads exclude archived
reports. Kevin approved extending these account grants to RF-512
[report-state reads](support-report-state.md). Each endpoint checks its own
resource binding. Approval, execution, and recovery require separate authorization.

## Closed response and failures

`SupportRun` version 1 contains run/report IDs, provider mode, simulation label,
operation-pending flag, and ordered events. Each event exposes its saved ID,
stage, sequence, timezone-aware timestamp, type, and defined RF-310 metadata.
Report text, prompts, arguments, checkpoints, diagnosis, and exceptions stay private.

Validate checkpoint run/report, intake stage, event run, unique IDs, and
contiguous sequence. Preserve saved order and timestamps; reject inconsistent
history. An accepted run without checkpoint/events returns an empty array,
which says nothing about completion. Missing or inaccessible runs return 404.

Errors use the shared envelope: 401 invalid/missing identity, 403 unsupported
role, 404 missing or inaccessible report/run, 422 invalid path UUID, and 503
unavailable infrastructure or invalid saved/configuration data. Foreign and
nonexistent reports are indistinguishable.

Registry and checkpoint reads are separate snapshots. History may advance
during a request; refresh reads the latest saved events. `operation_pending` is
rechecked before return but cannot prove a worker is running. Reconciliation
requires a separate mutation.

Only intake events have a trusted registry binding today. Approval timelines
remain separate until their integration supplies a reviewed durable binding.
The UI must not imply approval or tool events exist for these intake runs.
RF-504 can integrate this endpoint into an authorized internal view; it must not
place internal events on customer screens or customer SSE streams.

## Verification and review

`pnpm check` passed formatting, lint, generated-client drift, strict Python and
TypeScript checks, production web build, all 517 collected backend tests, and
47 frontend tests against a task-owned disposable PostgreSQL/pgvector database.
The final expanded focused suite passed all 14 support-read tests; formatting,
lint, strict API types, and whitespace checks passed after those additions.
Tests cover real PostgreSQL checkpoints, account isolation,
missing/empty timelines, archival, access revocation, repeated reads, restoration
through a fresh reader, and unchanged checkpoint history/provider call counts.
Additional cases reject corrupt bindings/order/metadata, preserve saved clock
timestamps, and sanitize unavailable infrastructure. No live model calls ran and
the project database was not changed.

Kevin accepted the final PAIR implementation review on 2026-10-12 after reviewing
the intake service, locking, persistence, and stream transport. RF-513 is DONE;
RF-504's real browser/API/PostgreSQL integration passed on 2026-10-12;
see `execution-timeline-ui.md`.
