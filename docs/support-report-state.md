# Support report-state lookup (RF-512)

Status: DONE. Kevin approved the authorization and response contract on
2026-10-12 and accepted final PAIR implementation review on 2026-10-13.

## Endpoint

`GET /support/issue-reports/{report_id}/state` reads current report state,
including archived reports. It works whether or not an intake run exists.
The closed, versioned Pydantic response is included in the generated API client.

Illustrative archived response:

```json
{
  "version": 1,
  "report_id": "00000000-0000-0000-0000-000000000001",
  "customer_account_id": "00000000-0000-0000-0000-000000000002",
  "status": "deleted",
  "archived": true
}
```

`status` uses the existing `IssueReportStatus` enum. `archived` is derived from
`status == "deleted"`; the response must reject disagreement. An active report
returns its stored status and `archived: false`. The account ID identifies the
report's owning account; clients cannot supply account scope for authorization.

This is a state lookup, not a full report detail response. It exposes no report
text, submitter identity, checkpoints, or intake data. Current storage has no
archive actor/time history. Generic `updated_at` must not be represented as an
archive timestamp. The endpoint does not restore or modify a report.

## Approved access contract

Authenticate the bearer token against a current database user. Require the
support role and an explicit grant for the report's current owning account.
Use the validated `DEMO_SUPPORT_ACCOUNT_IDS` mapping introduced by RF-513,
explicitly extending those account grants to this separate read operation.
No support user receives access merely by having the support role.

Scope the database report query by the allowed account IDs, including archived
rows. Missing grants deny access. Malformed grant configuration must never
broaden access. The service rechecks current identity, role, grants, and report ownership
before returning the response in a fresh database session, following the support
timeline pattern. If ownership changes between reads, it rejects the response;
if status changes within the same account, it returns the current status.
These checks establish access at read time; they cannot prevent a later change.

Timeline and state reads remain distinct operations. This extension grants no
proposal, decision, execution, recovery, or mutation permissions. Customer routes
continue excluding archived reports, and a customer 404 still cannot establish
that a report was archived.

## Errors

Use the existing safe error envelope:

| Condition | HTTP status |
| --- | --- |
| Missing, invalid, or revoked identity | 401 |
| Authenticated non-support role | 403 |
| Unknown report or report outside granted accounts | 404 with the same message |
| Invalid report UUID | 422 |
| Database unavailable, malformed grants, or invalid saved response data | 503 |

The lookup must not depend on model/provider configuration, checkpoint setup,
or the presence of an intake run. It reads report persistence directly and does
not construct a graph, advance a workflow, or write data.

## Implementation and verification

Database-backed API tests cover permitted active and archived reads, reports
without intake runs, missing/foreign reports with identical unavailable errors,
customer-role rejection, missing/invalid credentials, absent/malformed grants,
and revoked credentials/role/account access. They verify the closed response and
status/archived invariant, unchanged customer archive behavior, and unchanged
stored report state after repeated reads. Infrastructure failures return safe errors.

The test database contains only report-related tables for these endpoint tests;
no intake run or checkpoint table is needed. Other cases change status or
ownership between reads to check freshness and binding. A corrupted loaded value
is injected to verify response validation without bypassing database constraints.

Code lives in `apps/api/src/api/support/reports.py`, with shared current account
grant checks in `support/access.py` and transport mapping in `support/router.py`.
The application lifespan installs the reader using its session factory and clears
it at shutdown. The existing timeline reader shares grant parsing and preserves
its report/run binding checks. No migration or frontend change is required.

On 2026-10-12, `pnpm check` passed all **540 backend tests and 103 frontend
tests**, with no skips, against a disposable PostgreSQL/pgvector database.
Formatting, lint, strict Python/TypeScript checks, production web build, and
generated-client drift checks passed. The 22 new endpoint/schema cases and the
existing support timeline suite passed as part of that run. Application lifespan
tests also verify reader installation and cleanup.

Kevin accepted final PAIR implementation review on 2026-10-13. No live model call
ran and no project database data was changed.
