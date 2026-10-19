# Request limits (RF-706)

RF-706 uses shared PostgreSQL counters, as Kevin approved on 2026-10-18.
Counters apply across workers, sessions, and API restarts. Input limits and
request reservations run before endpoint work.

## Input limits

The API reads at most 65,536 bytes before parsing a request or running endpoint
work. This counts encoded body bytes, including JSON escaping. Existing field
limits still apply, such as 5,000 characters for report descriptions and 2,000
characters per clarification answer.

The body cap applies even when Content-Length is missing or smaller than the
actual body. Oversized requests return HTTP 413 with `payload_too_large` in the
shared error envelope. Invalid or duplicate Content-Length headers return 400.
Reading a body has a ten-second deadline; incomplete uploads return HTTP 408
with `request_timeout`. Disconnected uploads never reach endpoint work.

The middleware buffers bounded input before dispatch. Subsequent SSE response
streaming and disconnect detection remain available. CORS headers and request
IDs are included on rejections. The browser explains upload and rate errors
without automatically repeating a mutation; `Retry-After` is exposed through
CORS for rate-limit responses.

These controls bound application input. Hosting still needs connection and
transport limits; a server can receive an individual chunk before the
application rejects it.

## Rate limits

Each counter has a sixty-second window starting with its first accepted request.
The defaults suit a controlled demonstration:

| Counter | Requests per window | Applies to |
| --- | --- | --- |
| Connection address | 120 | Auth, admin, report, intake, and support paths, including invalid requests |
| Authentication by address | 20 | Login and invitation redemption combined |
| Signed-in user | 120 | Customer reports/intake, support reads/actions, and admin operations |
| Changes by user | 30 | POST, PUT, PATCH, and DELETE on those authenticated routes |
| Changes by customer account | 30 | Customer mutations across users in the same account |
| Model operations by user | 10 | Intake start, clarification, recovery, and evidence analysis combined |
| Model operations by customer account | 10 | Customer intake operations across users in the same account |
| Model operations across the application | 60 | All intake and evidence operations across users and accounts |

Login also retains its existing ten-attempt, ten-minute email limit. Changing
emails does not reset the address counter. Changing sessions does not reset user
or account counters. Logout has the address limit but can still revoke a session
when the user's mutation limit is exhausted. Health/readiness probes and CORS
preflight do not consume rate allowance.

An authenticated request reserves its applicable user/account/model counters in
one transaction. If any is exhausted, that transaction rolls back. The earlier
address reservation remains consumed. Accepted reservations are not refunded
when validation, authorization, or later endpoint work fails. Repeating an
operation ID also consumes allowance, even when the service reuses a saved
result. Saved reads remain available when only the mutation/model limit is
exhausted; the overall user/address limits still apply.

A rejection returns HTTP 429, `rate_limited`, and a `Retry-After` duration in
seconds. Requests do not wait for quota to become available. A missing counter
table or unavailable database returns 503 before authenticated work or provider
dispatch. Missing identity on a private route can still return 401. Counters
commit independently of workflow transactions; cancellation after reservation
can consume allowance without completing the operation.

The database uses its clock and atomic conditional updates. Independent workers
cannot each grant a full separate allowance. Multi-counter reservations take
locks in a stable order and have bounded statement, lock, and transaction waits.
Inactive windows older than a day are pruned in batches of at most 100 per
successful reservation. Stored subjects are domain-separated SHA-256 digests;
rows contain no raw address, user ID, token, body, or provider content. These
hashes are pseudonymous identifiers, not a claim of anonymization.

## Configuration and deployment

Migration `0009` creates `request_limit_windows`. Apply migrations before using
the updated API:

```bash
uv run --directory apps/api --env-file ../../.env alembic upgrade head
```

Set `REQUEST_LIMITS` to a JSON object in the API environment to override defaults.
Compose forwards the root `.env` value. For example:

```dotenv
REQUEST_LIMITS='{"peer":120,"authentication":20,"user":120,"mutations":30,"model_operations":10,"global_model_operations":60}'
```

Each field accepts an integer from 1 to 10,000. Omitted fields use defaults;
empty configuration uses all defaults. Unknown fields or invalid values prevent
app startup. Keep the same configuration on every worker. Updates affect new
checks, including counters already in their current window.

The supported `python -m api.server` entry point disables Uvicorn's proxy-header
rewriting. The limiter uses the transport peer and ignores caller-supplied
`Forwarded` and `X-Forwarded-For`. Behind a reverse proxy, clients therefore
share that proxy's address allowance. Hosting must supply any separate public
client-address controls; enabling forwarded-header trust requires an explicit
trusted-proxy design. A custom Uvicorn command that rewrites the peer falls
outside this address guarantee.

## Limits of this protection

These are fixed windows, so traffic can burst on either side of a reset. They
count HTTP operations, not individual paid provider attempts or dollars. One
accepted operation may make bounded retries or embedding batches. RF-705 retains
those actual attempts; provider spend caps remain a separate operational control.
There is no aggregate active-stream/job limit, storage quota, or report-list
pagination in RF-706. Hosting still needs connection and transport controls.
Standalone evaluation and ingestion commands do not use these HTTP counters.

## Verification

Nine input tests cover announced and chunked overflow, understated lengths,
malformed lengths, exact-boundary acceptance, upload timeout, disconnect, and
application error headers. Three frontend cases exercise actual API clients
against HTTP 408, 413, and 429 and verify that each request is sent once.
Seven PostgreSQL/HTTP cases cover independent-worker concurrency, new limiter
instances, expiry, policy/subject isolation, atomic multi-counter rejection,
bounded cleanup, authentication abuse across emails and forwarded headers,
pre-parse rejection, probe exemptions, and unavailable storage. Five intake
cases prove user/account/global model-operation limits, token rotation, reads
after rejection, and no run/provider dispatch for blocked work. Five invalid
configuration cases reject startup rather than disabling limits.

On 2026-10-18, `pnpm check` passed formatting/lint, generated-client drift,
Python/TypeScript checks, production build, all 864 backend tests, and all 206
frontend tests with no skips on disposable PostgreSQL 17/pgvector. Migration
`0009` upgrade/rollback and ORM drift passed in a separate disposable database.
RF-706 is DONE under DELEGATE ownership. The project database is unchanged; no
live provider calls or deployment were performed.
