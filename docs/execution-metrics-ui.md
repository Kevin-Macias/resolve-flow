# Execution metrics display (RF-509)

Status: Kevin approved this scoped contract on 2026-10-13. Implementation and
verification are complete; RF-509 is DONE within this scope. Ownership is DELEGATE.

## Saved data and scope

Show metrics from the latest saved intake extraction record in the support
report workspace. The checkpoint stores `ExtractionCallRecord` on extraction
success or handled failure. A later extraction replaces that field, so this
view is explicitly labeled **Latest extraction only**, never a run total.

Display configured model, prompt ID/version, attempts, and input/output/total
tokens when returned by the provider. Token usage belongs to the final returned
provider response; it does not account for all retry attempts. A missing value
means **Not recorded**, while an actual recorded zero remains zero.

Latency and estimated cost are displayed as **Not recorded**. Existing records
contain neither measurement. Do not derive model latency from timeline timestamps,
which include other work and human waits. Do not calculate cost from current
prices or treat offline execution as a measured zero-dollar provider call.

Offline mode is labeled **Offline simulation**. A configured model name is not
proof of a live call. Missing records show **No saved extraction metrics yet**;
an accepted pending operation may leave the previous saved record visible and
must be labeled accordingly. Evidence analysis, embedding calls, and approval
execution are outside this latest-intake-extraction view.

RF-705 adds a separate [attempt history](model-accounting.md) with latency,
retries, and versioned estimates. Open **Show model attempt history** to load
those records; this latest-extraction snapshot keeps its original contract.
Kevin approved RF-509's unavailable values rather than pulling accounting into
that earlier ticket.

## Read contract

`GET /support/issue-reports/{report_id}/execution-metrics` uses the existing
support-user account grants and current report/run binding. Recheck authorization
before returning protected data, as with support run reads. Archived reports
remain readable within those grants. Customer endpoints and projections remain
unchanged.

Return a closed, versioned response bound to the report and optional intake run,
with provider mode, operation-pending state, explicit latest-extraction scope,
and an optional validated metrics record. A permitted report without a run or
record returns an empty state. Invalid saved data fails safely; it must not be
silently converted to an empty record or repaired. Read only saved checkpoints;
refresh must not invoke a graph, provider, or tool.

Only expose the fields needed for this display. Exclude report text, prompts,
model output, provider error messages, and credentials. Validate nonnegative
integer usage and attempts, nonempty model/prompt identifiers, and response
report/run binding. Do not invent missing fields for legacy records.

## UI and verification

Place a metrics section after the approval area in the existing support report
page. Use the generated API types and runtime Zod validation. Support loading,
empty, saved, stale/read failure, and unavailable states, with explicit refresh.
Session/report changes isolate requests and caches. Revoked access clears the
metrics and the other protected sections together; invalid responses hide the
affected metrics.

Backend tests cover authorized and denied reads, missing run/record, archived
reports, saved success/failure records, nullable versus zero usage, malformed
saved data, changed grants, and read-only behavior. Frontend tests cover values,
scope/usage caveats, offline labeling, missing latency/cost, loading/empty/error,
refresh, validation, late responses, and shared access loss. Verify persisted
records and reload through real HTTP/PostgreSQL with a production browser;
ordinary checks require no live provider calls.

## Implementation

`apps/api/src/api/support/metrics.py` validates and projects the saved extraction
record. The support router exposes the read; database lifespan shares the reader
through app state. The reader holds configuration and the session factory, not
per-report records. No database migration or additional model call is needed.

`apps/web/src/features/metrics/` contains the typed client, runtime response
schema, panel, and interaction tests. The existing support report page mounts
the panel after approval and shares its access-loss handling. Each report/session
has its own query key; requests receive abort signals. Disconnection marks saved
values stale until a successful subsequent read, including when Query pauses a
request rather than throwing a network error.

The configured-model label describes the saved configuration, not a verified
provider-resolved model identity. Final-response usage can survive a handled
extraction failure. Failed provider attempts may have no reported usage, and a
later extraction replaces the previous record. These values cannot establish a
complete bill or total run usage.

## Verification

Backend tests use disposable PostgreSQL and real checkpoints. They cover empty
and pending runs, saved records, handled extraction failure, latest-round
replacement, zero and missing usage, invalid records, authorization/revocation,
archived reads, reader recreation, and unchanged checkpoint history on refresh.
Frontend tests cover saved/empty/pending states, nullable values, offline and stale
reads, recovery, invalid responses, access loss across the protected report page,
and late session/report responses.

The production Chromium walkthrough uses real HTTP and persisted checkpoints.
It covers saved metrics, nullable usage, explicit unavailable accounting, GET-only
refresh, reload, desktop/mobile layout, offline recovery, no-intake reports,
archived reads, and foreign-account access loss. No HTTP interception or live
provider calls are needed. Complete check results are recorded in the roadmap.



`pnpm check` passed formatting/lint, generated-client drift, Python/TypeScript
types, the production build, all **601 backend tests**, and all **169 frontend
tests**, with no skips. RF-509 adds 16 backend and 17 frontend tests. PostgreSQL
16 / pgvector 0.6.0 ran from a disposable `/tmp` instance; the project database
was unchanged. This ticket requires no additional migration or model settings.
