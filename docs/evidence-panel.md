# Evidence panel (RF-506)

Status: implemented and verified. Kevin approved the separate preliminary support
analysis and its access contract on 2026-10-13.

## Goal and integration boundary

The support report page shows saved preliminary analysis and its source passages.
Each passage exposes the title, document version, source path, heading/line range,
exact excerpt, rank, and named score. Claims distinguish supported statements,
inference, missing evidence, and conflict, with supporting/contradicting references.
Fictional and historical sources retain visible labels. Similarity is not
confidence in a diagnosis; fixture scores do not measure semantic relevance.

RF-506 connects RF-407/408 retrieval, RF-409 citation verification, and RF-411's
analysis boundary to durable support operations. Kevin approved this separate
support analysis instead of the original automatic workflow diagnosis prerequisite.
The panel labels its input as unconfirmed customer observations requiring human
review. Customer summary confirmation and automatic workflow diagnosis remain
separate work; intake still stops at `needs_confirmation`.

## Operations and persistence

- `POST /support/issue-reports/{report_id}/evidence-analyses` explicitly retrieves,
  analyzes, verifies, and saves evidence. Its only input is an operation UUID.
  The server derives query text, service, permissions, and active revisions.
- `GET /support/issue-reports/{report_id}/evidence-analysis` reads the latest saved
  result. Opening or refreshing the page never starts model work. An authorized
  report with no analysis returns `absent`, separately from a successful empty
  search, a failed analysis, or an interrupted operation.

Migration `0004` adds `evidence_analyses`, indexed by report, with a unique operation
UUID per report. Records bind analysis identity, account/report, creation time,
provider mode, input hash, retrieved ranks/metrics, verified citations/claims,
and immutable source snapshots. Full input and source records stay internal;
the HTTP response contains the verified evidence projection.

The input hash binds original description, current service code, intake identity
and revision when present, and accepted questions/answers. Unsent drafts and
unconfirmed extraction summaries are excluded. A changed input marks the saved
result as based on older observations. Refresh reads that result; requesting a
new analysis is an explicit action.

Analysis shares intake's per-report PostgreSQL advisory lock so accepted turns
cannot change during generation. It commits `pending` before invoking adapters.
Repeating a UUID reuses its outcome without another provider call; concurrent
commands receive a conflict. The browser guards duplicate submissions and keeps
an uncertain UUID until its outcome is observed. Mutations never retry automatically.

Handled failures save `failed` without result content. Worker interruption leaves
`pending`: reads and UUID replay expose that state without resuming it, and new
operations are blocked. Recovery requires a separately reviewed contract and is
not exposed by this panel. A failed result permits an explicitly requested new
operation.

## Access and source policy

Existing explicit support account grants extend to evidence generation and reads.
Both require a current support identity and access to the report's current account,
including archived reports. Report access is required even if only public sources
match. Client input cannot choose account scope or source locations.

Retrieval permits public and internal sources plus account-specific sources for
this report's account only, rather than every account the support user can access.
Active revisions come from the trusted manifest. Superseded sources are excluded
before ranking, `top_k=5`, and an affected service supplies an exact service-code
filter. No relevance threshold has been introduced.

Before publication, recheck identity, grants, ownership, input binding, and current
source metadata. Reads repeat current report/account checks, validate saved input
binding and every excerpt/hash/location, and reassemble claim references. They
also check current source policy. A removed source or one now belonging to another
account withholds the analysis. A historical version may remain visible when still
authorized, with an explicit historical label; it is not presented as current advice.
Snapshots never grant continuing access. Checks establish access at read time;
they cannot prevent a later permission change.

Missing/invalid credentials return 401, a non-support identity 403, and unknown or
ungranted reports 404 with the same safe error. Invalid input returns 422, busy or
unresolved operations 409, and infrastructure/configuration/validation failures 503.
Provider errors and source contents are not echoed in errors.

## Providers and setup

Apply migration `0004` before using the panel. Reports without an intake run need
no checkpoint setup. `EVIDENCE_PROVIDER_MODE=offline` is the default: real verified
corpus passages receive deterministic `fixture` ranking, and scripted analysis
returns a missing-evidence claim. It performs no semantic diagnosis.

The API loads `knowledge/manifest.json` and its Markdown files from
`KNOWLEDGE_ROOT`, defaulting to the repository root locally. Docker includes the
corpus and sets its root to `/app`.

Optional live mode requires `EVIDENCE_PROVIDER_MODE=live`, `EVIDENCE_OPENAI_MODEL`,
and provider credentials. Explicitly index the configured corpus using the
[indexing command](retrieval-integration.md) first. A read-only preflight checks
complete indexing before live search. Queries beyond the existing 512-token
embedding budget fail safely without truncation. Provider work has a 60-second
operation timeout. Clients are constructed only for an explicit live POST.

The analysis adapter sends RF-411's fixed instructions separately from verified
JSON source data, requests claim-only output, and validates references through
RF-409. The live wire schema requires every field, with nullable explanations,
as required by [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Invented sources, changed excerpts, and inconsistent claim bindings fail closed.
Citation integrity does not establish semantic support. General runbooks and
fictional investigations cannot prove this particular report's archival; RF-512
remains the separate current-state lookup. Live relevance and model injection
resistance remain unmeasured.

## Panel behavior and code map

The panel distinguishes loading, absent, pending, failed, empty evidence, ready,
older-input, and unavailable states. Temporary read errors can retain visibly stale
results while commands are disabled. Invalid responses clear evidence. Access loss
clears protected evidence and the combined support view; ended sessions or previous
reports cannot restore late results. Titles, paths, excerpts, and model text render
as plain text. The panel never executes source HTML or links arbitrary file paths.

- `api/support/evidence.py` authorizes, binds observations, saves operations, and
  verifies saved results. `evidence_runtime.py` owns corpus loading and adapters.
- `evidence_models.py` and `evidence_schemas.py` define persistence and HTTP contracts.
- `apps/web/src/features/evidence/` holds shared Zod validation, a generated-client
  wrapper, `use-support-evidence.ts`, and the rendering-only panel.

## Verification

On 2026-10-13, root `pnpm check` passed **563 backend and 120 frontend tests**, with
no skips, against disposable PostgreSQL 16 and pgvector 0.6.0. Formatting, lint,
Python/TypeScript checks, generated-client drift, and production build passed.
Migration upgrade, rollback, re-upgrade, and `alembic check` passed. The project
database was unchanged. Docker was unavailable; its configured PostgreSQL 17 /
pgvector 0.8.7 combination was not exercised here.

The 23 new backend cases cover operation reuse/concurrency, interruption, empty
search versus failure, input freshness, access/source-policy changes, forged
excerpts, refusal/empty output, and strict provider schema wiring. The 17 frontend
cases cover display states, provenance, plain text rendering, uncertain writes,
duplicate submissions, response validation, stale reads, and session/access loss,
including removal of the combined support view.

Chromium used the production build with real HTTP and PostgreSQL results, without
HTTP interception. Explicit analysis, read-only refresh, reload, API process restart,
desktop/mobile layout, older observations, archival, revoked support role, foreign
report denial, and reports without intake passed. No runtime errors occurred.
All verification used deterministic adapters; no live model or embedding call ran.
