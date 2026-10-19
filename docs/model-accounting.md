# Model cost and performance (RF-705)

PAIR work, 2026-10-18. Kevin selected versioned pricing configuration and stopping
before a live call when its durable accounting start cannot be saved.

## Goal and scope

Keep every application model attempt across intake rounds, retries, and process
restarts. Record configured/resolved model identity, prompt identity/version,
provider mode, reported tokens, provider latency, retry number, and a saved cost
estimate with its pricing basis. Preserve the existing RF-509 latest-extraction
view; expose complete attempt history separately to authorized support users.

Intake extraction and preliminary evidence work are separate scopes. Evidence
analysis and embedding requests belong to the evidence operation, even if it has
no intake run. Standalone evaluation/ingestion commands remain separate from
application report accounting. This is a usage estimate, not a provider bill.

## Current code and gaps

- `ExtractionCallRecord` retains one extraction's final response usage and attempt
  count. Checkpoint replacement loses earlier rounds and retry usage.
- The provider result includes a resolved model name, but the latest-extraction
  display uses configured identity. Cost estimation needs explicit identity and
  versioned rates rather than whatever prices happen to be current at read time.
- Preliminary evidence generation and embedding have separate adapters. The
  current embedding adapter discards SDK usage. Missing provider measurements
  must remain unavailable until captured at the actual request boundary.
- RF-704 logs help trace work but are not durable accounting records. Request
  IDs can change across recovery; saved operation IDs remain stable.

## Attempt lifecycle

Save an attempt start in a separate committed transaction before dispatch. If
that write fails, make no provider call. Each actual retry gets its own record;
a logical call groups attempts and links to its authorized report and operation.
Save the outcome and measured provider duration after the provider returns or
raises, independently of workflow checkpoint publication.

Provider response received, refusal, timeout, provider error, cancellation, and
an unfinished start remain distinct. A response can consume tokens even when
application schema validation fails. Record available usage before that result
is rejected. Do not infer zero usage or cost from an exception.

If completion cannot be saved, retain the committed start and report accounting
as unconfirmed. Do not silently discard accounting failures or automatically
replay a paid call just to repair its record. Explicit workflow recovery can
make a new attempt when the original model result did not survive; this is not
an exactly-once guarantee for provider billing.

## Estimates and incomplete totals

Use decimal arithmetic and a versioned operator-supplied USD rate configuration.
Save the pricing basis used for each estimate. A later rate change must not
rewrite saved estimates. Match model identity explicitly; never guess rates for
an unknown model. No rate, missing usage, unsupported usage details, or an
interrupted call means cost is unavailable for that attempt.

Input/output tokens and cached-input details must use provider-reported values.
Embedding output tokens are not applicable. Offline records are labeled synthetic
and do not become measured zero-dollar live calls. Legacy checkpoints cannot be
converted into complete per-attempt history after the fact.

A summary shows known token/cost subtotals, measured duration, attempt/retry
counts, and missing/pending counts. A partial subtotal is labeled partial; it is
not a complete run bill. Provider duration excludes retry backoff, database work,
and human waits. Unknown durations are not counted as measured zeros.

## Access and privacy

Reuse current support grants, report/account binding, archived-report access,
and fresh access rechecks before returning metrics. Reads never run a graph,
provider, or tool. Customers do not receive internal accounting records.

Store metadata only. Exclude report/source text, prompts, outputs, credentials,
and raw provider exceptions. Operational logs keep RF-704's existing field
policy; recording model names and usage in a protected accounting table does
not add those fields to routine logs.

## Verification contract

- Record each retry and each clarification round separately; provider failures,
  refusals, and invalid application output retain available usage.
- A failed start write makes zero provider calls. An interrupted completion
  retains an unknown record across process restart.
- Versioned rate changes preserve prior estimates. Known zero and missing values
  remain distinct; incomplete, offline, and legacy scopes are labeled.
- Authorized support reads work after restart and recheck access; foreign-account,
  customer, and revoked-grant reads cannot expose records or invoke providers.
- Browser history/totals validate the generated contract, isolate session/report
  caches, and show partial and unavailable states clearly.
- Migration upgrade/rollback, ORM drift, lint/types, client drift, full regression
  checks, and isolated PostgreSQL tests pass without live provider calls.

Implementation and automated verification are complete. Kevin accepted final
PAIR review on 2026-10-18. The existing [latest-extraction contract](execution-metrics-ui.md) remains available
alongside the new history.

## Implemented storage and read API

Migration `0008` adds `model_call_attempts` and nullable accounting coverage
markers on intake runs and evidence analyses. New application operations mark
coverage explicitly; existing rows remain legacy. Attempt starts and completions
commit independently of workflow checkpoints. Each embedding HTTP batch has its
own call ID and attempt number 1, with the parent embedding call ID retained;
batches are not counted as retries.

`GET /support/issue-reports/{report_id}/model-accounting?offset=0` returns report
subtotals, separate totals by intake run and evidence operation, and up to 50
attempts. `next_offset` selects the next page. All attempt rows are bound to the
current report/account and a saved intake/evidence scope; access is checked again
before return. Reads never repair records or recalculate their saved estimates.
Concurrent work can change history between page reads; refresh for current data.

The existing support metrics panel keeps RF-509's latest-extraction snapshot.
Select **Show model attempt history** to load RF-705 records. The history view
shows partial subtotals, unavailable values, offline measurements, unfinished
starts, legacy coverage, and pagination. Model names and prompt versions are
protected accounting metadata; prompt text and model output are not stored.

## Pricing setup

Set `MODEL_PRICING` in the API environment. Compose forwards the root `.env`
value; host processes need the same environment loaded. This example uses
illustrative rates, not published prices:

```dotenv
MODEL_PRICING='{"version":"example-only-v1","currency":"USD","rates":[{"provider":"openai","model":"your-model-snapshot","input_per_million":"1.00","output_per_million":"2.00","cached_input_per_million":"0.50"}]}'
```

Rates are USD per million tokens, stored as decimal strings. Supply your reviewed
model names and rates. When the provider reports a resolved model, match that
identity; otherwise match the configured model. Missing or unmatched rates leave
estimates unavailable. Cached input needs reported cached-token counts and, when
nonzero, an explicit cached-input rate. Embedding input uses reported usage, with
no output tokens or cached-input charge.

Changing any pricing-card content requires a new version after the old card has
been saved. Concurrent starts serialize that version check. Each attempt keeps
the complete card snapshot and, when priceable, the selected rate and exact
saved estimate. Changing environment values affects new accounting scopes only;
reads never reprice history. Missing configuration permits calls with unavailable
estimates; malformed configuration stops a live operation before dispatch.

Apply migrations before running the updated API:

```bash
uv run --directory apps/api --env-file ../../.env alembic upgrade head
```

If accounting cannot save an attempt start, the paid call is not dispatched.
If completion cannot be confirmed, the start remains and the application reports
an interrupted operation. Recovery follows the existing explicit workflow
commands; it does not invent usage or silently retry billing reconciliation.
Routine logs report the fixed `accounting_unavailable` failure code and keep
the existing metadata-only log policy.

## Implementation checks

Targeted PostgreSQL tests exercise actual separate commits, frozen pricing,
partial-response usage, each retry, subsequent intake rounds, access revocation,
legacy coverage, embedding batches, and distinct timeout/cancellation outcomes.
A subprocess exits immediately after its attempt start commits; a new reader
still sees the unknown start. Forced connection failures prove that a failed
start does not dispatch and a failed completion retains its durable start.
HTTP tests verify serialized numeric estimates without exposing the full pricing
card. DOM tests cover partial and zero estimates, offline labels, invalid totals,
foreign report bindings, access loss, stale recovery, explicit loading, and late
session responses. No live model calls are required.

Migration `0008` upgrade/rollback and ORM drift passed on disposable PostgreSQL.
Final full-check results are recorded in the [roadmap](roadmap.md). The project
database has not been migrated, and no hands-on production-browser walkthrough
or live provider/billing comparison has been performed for RF-705.

Final verification on 2026-10-18: `pnpm check` passed formatting/lint, generated
client drift, Python/TypeScript checks, production build, all 838 backend tests,
and all 203 frontend tests with no skips on disposable PostgreSQL. This includes
17 new accounting cases and 11 new frontend cases. Migration `0008` roundtrip
and ORM drift passed separately. Kevin accepted final PAIR review on 2026-10-18;
RF-705 is DONE.
