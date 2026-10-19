# Structured correlated logging (RF-704)

Kevin approved metadata-only JSON logs to server stdout on 2026-10-18, with
search, collection, access, and retention handled by the hosting environment.
Kevin accepted final PAIR implementation review on 2026-10-18.

## What logs answer

Follow a request into an authorized workflow run, model attempts, and approved
tool execution by filtering identifiers. Recovery gets a new request ID while
retaining saved run and execution IDs. Logs complement saved workflow history;
durable database receipts remain the authority for committed effects.

Each line is one JSON object, for example:

```json
{"timestamp":"2026-10-18T10:42:02Z","level":"INFO","event":"execution.completed","component":"execution","request_id":"11111111-1111-4111-8111-111111111111","run_id":"22222222-2222-4222-8222-222222222222","execution_id":"33333333-3333-4333-8333-333333333333","outcome":"success","duration_ms":820.0}
```

A host log viewer can filter `request_id` for one request, `run_id` across
requests, `execution_id` across retries/recovery, or `outcome` and `duration_ms`
for failures and slow work. No local viewer, collector, or log database is added.

## Fields and privacy

[`observability`](../apps/api/src/api/observability/__init__.py) defines a closed,
validated event schema. Unknown fields, arbitrary objects, invalid identifiers,
and nonfinite durations are rejected before formatting.

| Field | Meaning |
| --- | --- |
| `timestamp`, `level`, `event` | UTC timestamp, severity, and application-defined event name |
| `request_id` | Server-generated UUID, returned as `X-Request-ID`; caller-selected IDs are ignored |
| `method`, `route`, `status_code` | Recognized method, matched route template, response status; unmatched routes use `<unmatched>` |
| `component` | Fixed application area, such as intake, extraction, analysis, embedding, or execution |
| `run_id`, `operation_id` | UUIDs attached after the application establishes access and saved bindings |
| `call_id`, `attempt` | Logical model-call UUID and provider retry number |
| `execution_id` | Approved simulation idempotency UUID, retained during recovery |
| `outcome`, `failure_code` | Fixed values describing success, error, timeout, cancellation, disconnection, rejection, receipt reuse, or unknown tool outcome |
| `duration_ms` | Nonnegative elapsed monotonic time |

Logs exclude headers, cookies, credentials, email addresses, bodies, query strings,
raw URLs, report/answer/source text, prompts, model output, tool arguments, and
raw exception messages/tracebacks. Configured model names and provider response
IDs are also omitted. Persisted model accounting is covered by
[RF-705](model-accounting.md).

Correlation uses Python context variables, isolated between concurrent requests
and reset on exit. No credentials or request IDs are added to graph checkpoints.
Authorized intake reads attach the run ID to their request, including SSE.
Streaming retains correlation through the response lifetime and logs a summary,
not individual customer snapshots. Cancellation, disconnection, and an error
after streaming headers preserve the status already sent. A server error before
headers records 500 and the error response carries the same request ID.

## Events and boundaries

| Events | Boundary |
| --- | --- |
| `request.started`, `request.completed` | HTTP handling, including streaming lifetime |
| `run.started`, `run.completed` | Authorized intake execution, approval processing, or preliminary evidence operation |
| `model.started`, `model.completed` | Extraction including output validation, live evidence generation, or an embedding adapter call |
| `provider.started`, `provider.completed` | Each extraction provider attempt, including timeout/retry outcomes |
| `tool.started`, `tool.completed` | Validated approved adapter dispatch; success means the adapter returned, not that a receipt committed |
| `execution.started`, `execution.completed` | Durable simulation processing, including reuse and unknown outcomes |
| `execution.intent_ready` | Application intent is available after the reserve transaction |
| `execution.destination_committed` | The destination transaction returned with its committed effect/receipt |
| `execution.result_committed` | The application result transaction completed |
| `execution.receipt_reused` | A destination receipt was reused without another adapter dispatch |
| `api.error` | Sanitized unexpected API failure |
| `runtime.message`, `runtime.error` | Sanitized server/dependency record; original prose and tracebacks are discarded |

An approval rejection is a valid reviewed outcome and does not dispatch a tool.
Interrupted execution can log an unknown outcome even when a destination receipt
exists; recovery reads durable state. A process kill may leave only a start
event. Operational logs are neither an exactly-once ledger nor a tamper-proof
audit store.

## Running and collecting logs

Use the supported entry point so application, Uvicorn, and dependency logging
share the safe formatter:

```bash
# From the repository root; development reload
pnpm dev:api

# From apps/api; server process, also used by Docker
uv run python -m api.server
```

`PORT` defaults to 8000. `--host`, `--port`, and `--reload` are supported.
The root development command binds localhost; the container entry point binds
all interfaces. Apply existing database/checkpoint setup before workflow use.

[`server.py`](../apps/api/src/api/server.py) disables raw Uvicorn access logs;
application request events replace them. The
[logging configuration](../apps/api/src/api/observability/config.py) sends JSON
to stdout and sanitizes server/SDK records without formatting their messages or
exceptions. This deliberately reduces dependency diagnostics to event/severity
and correlation. Importing the application alone does not configure output, so
offline evaluators and other CLI result artifacts remain clean.

Direct `uvicorn api.main:app`, custom logger handlers, external tracing, proxies,
and hosting-agent logs need their own configuration review. This application
policy cannot sanitize output produced outside its configured logging handlers.
Development runners may add prefixes when combining API and web output; use the
API process/container stream when configuring a JSON collector.

Hosting operators control search, retention, rotation, and access. Logs contain
correlatable identifiers and should be restricted to authorized operators.
Choose those deployment controls before exposing real customer data. The app
adds no external log delivery or retention job.

## Verification

[`test_logging.py`](../apps/api/tests/observability/test_logging.py) checks actual
JSON output, concurrent HTTP requests, route/header safety, errors, streaming,
cancellation, provider retries/output validation, tool failures, quiet CLI imports,
and repeatable server/SDK configuration. It also launches a disposable real
Uvicorn server and verifies that request secrets and raw error traces do not
appear in stdout/stderr.

[`test_logging_integration.py`](../apps/api/tests/intake/test_logging_integration.py)
checks real PostgreSQL-backed approval/recovery requests: different request IDs,
the same run/execution IDs, destination receipt reuse, and no second dispatch.
This database check requires `TEST_DATABASE_URL`. It passed against disposable
PostgreSQL on 2026-10-18 after Docker became available. Exact check results are
recorded in the [roadmap](roadmap.md).

Design references: [Python context variables](https://docs.python.org/3/library/contextvars.html)
and [OWASP logging guidance](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

After Docker became available on 2026-10-18, `pnpm check` passed formatting/lint,
generated-client drift, Python/TypeScript checks, production build, all 821
backend tests, and all 192 frontend tests with no skips. The PostgreSQL-backed
approval/recovery correlation case passed separately as well. All 26 logging
tests are included in the full run. Verification used a disposable PostgreSQL
17/pgvector container and left the project database unchanged. No live model
calls were made. The database verification gap is closed; Kevin accepted final PAIR review
on 2026-10-18, completing RF-704.

The separate [database initializer](container-startup.md) emits fixed
`database.initialize.started` and `database.initialize.completed` JSON events.
Raw migration/checkpoint subprocess output is suppressed. Startup failure uses a
fixed outcome and failure code, with no database URL or exception text.
