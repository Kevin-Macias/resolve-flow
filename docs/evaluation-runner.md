# Evaluation runner (RF-603)

Status: Kevin accepted final PAIR implementation review on 2026-10-15.
RF-603 is DONE. The runner executes the 20 approved fixture scenarios and emits
observations as JSON. The separate [RF-604 scorer](deterministic-metrics.md)
compares those observations with the approved labels.

## Run the approved cases

From the repository root, supply an explicit PostgreSQL evaluation database:

```bash
uv run --directory apps/api python scripts/evaluate_workspace.py \
  --database-url postgresql://localhost/resolveflow_evaluation \
  --output /tmp/resolveflow-workspace-observations.json
```

Alternatively, set `EVALUATION_DATABASE_URL`. The runner does not fall back to
the application's `DATABASE_URL`. The database role needs permission to create
and drop schemas. The command creates two uniquely named `rf_eval_...` schemas
for its tables/checkpoints and removes them when finished, including ordinary
failure and cancellation. It does not migrate or clear existing application
tables. Use a disposable evaluation database for convenient isolation.

Omit `--output` to print JSON to stdout. An output file must be new and its
parent directory must exist. Existing reports are never overwritten. The command
has no live mode or provider credentials requirement.

| Exit code | Meaning |
| --- | --- |
| 0 | All scenarios completed without executor errors; this is not a quality pass |
| 1 | A report was produced, with at least one scenario execution error |
| 2 | Invalid invocation, setup/input failure, or inability to publish the report |

The frozen case file is checked against its approved SHA-256 before execution.
Changing it requires a reviewed case-set version and corresponding loader update;
silently editing labels cannot change the evaluated baseline. Source hashes and
the case artifact are checked again after execution to detect changed inputs.

## What executes

| Target | Code exercised |
| --- | --- |
| Extraction and handled failures | `extract_issue_report` with literal fixture responses and bounded injected timeouts |
| Clarification | The intake graph with its real policy, saved pauses, ordered answers, and explicit incomplete continuation; in-memory checkpoints |
| Retrieval | Markdown preparation, fixture ranking, the checked retrieval service, and citation verification with trusted scope and revisions |
| Evidence analysis | Verified source serialization and the real output validator; extra approval/tool fields are rejected |
| Approval | Real FastAPI support proposal/decision/read endpoints through in-process ASGI, with isolated PostgreSQL state and checkpoints |

Approval starts from an actual completed fixture intake. The application assigns
proposal identities and fingerprints. A controlled simulated adapter records
dispatches, returns success, raises, or pauses according to the case setup.
The interrupted case cancels its request after adapter entry, recreates the
reader/runner over the same checkpoints, reads the saved receipt, and submits
the duplicate decision. It observes whether execution resumes; it never
fabricates an approved checkpoint to force an expected result.

This recreation is a same-process persistence check. Separate-process recovery
has its own workflow/API verification records; this runner does not claim a new
process-restart test. A hard process kill can leave its private schemas behind;
their generated names identify them for later operator cleanup.

The standalone runner temporarily installs fictional identity/grant configuration
in its own process and restores it during cleanup. It is not wired into API
requests and should not be embedded concurrently in an application server.

## Reading the report

The report records the case/spec hashes, code revision and dirty-worktree state,
source revision/content/metadata hashes, fixture/model/prompt/chunking settings,
and each case's target, group, expected labels, observed result, and execution
status. Ephemeral timestamps and application-generated identifiers can differ
between runs; compare behavior using the same input/configuration provenance.
Fixture mode is always explicit. Unrecorded latency and cost remain null.

Expected labels never configure the executor. Provider fixtures and operation
sequences drive execution; labels are copied into a separate `expected` field.
For example, changing an expected severity cannot cause the fake provider to
return that severity. The runner tests verify this separation.

`completed` means observations were collected. It does not mean they match all
expected outcomes. Its applicable assessments remain `unmeasured`; the separate
scoring command measures deterministic checks, and semantic judging remains
deferred. Irrelevant dimensions remain
`not_applicable`. An unexpected executor error records a fixed safe error code,
marks applicable assessments `error`, and allows later cases to continue.
Cancellation of the whole run propagates and cleans up instead of being counted
as a passing case. Reports exclude raw exceptions, database URLs, tokens, and
unauthorized passage text.

The observations exercise fixture mechanics. They do not establish live model
classification, question quality, retrieval relevance, or injection resistance.
The deferred live baseline and RF-605 judging require separate reviewed work.

## Implementation and verification

`apps/api/src/api/evaluations/` separates the frozen case/report contracts,
target executors, private database lifetime, and orchestration. The CLI lives at
`apps/api/scripts/evaluate_workspace.py`. Application behavior and the approved
case labels are unchanged.

The 24 focused tests cover all offline targets, two full case runs, actual
approval outcomes and dispatch counts, modified artifacts, expectation/output
independence, sanitized errors, partial runs, cancellation cleanup, explicit
database selection, rejection of live invocation, and output-file protection.
On 2026-10-15, `pnpm check` passed formatting/lint, generated-client drift,
Python/TypeScript checks, the production build, all 625 backend tests, and all
184 frontend tests with no skips. The 24 focused tests also passed separately.
PostgreSQL 16.15 and pgvector 0.6.0 ran from extracted packages in `/tmp`; no
system installation or project database changes were made. All 20 fixture
scenarios completed without executor errors; this records execution, not quality
scores.

Kevin accepted the implementation review on 2026-10-15. The review distinguishes
completed execution from quality scoring, preserves the first decision and
interrupted execution, and separates handled provider failures from executor
errors. The [case definitions](evaluation-cases.md) and
[evaluation specification](evaluation-specification.md) remain the authority
for labels and interpretation.
