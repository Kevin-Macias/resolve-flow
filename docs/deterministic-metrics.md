# Deterministic evaluation metrics (RF-604)

Status: Kevin accepted final PAIR implementation review on 2026-10-15.
RF-604 is DONE. The scorer compares fixture observations with the approved
[case labels](evaluation-cases.md) using the
[evaluation specification](evaluation-specification.md).

## Run the scorer

Generate observations with the [fixture runner](evaluation-runner.md), then score
them from the repository root:

```bash
uv run --directory apps/api python scripts/score_workspace.py \
  --input /tmp/resolveflow-workspace-observations.json \
  --output /tmp/resolveflow-workspace-metrics.json
```

Scoring runs offline without a database or provider credentials. It reads the
observations and local source snapshot; it does not execute scenarios again.
Omit `--output` to print JSON. Output files must be new, with an existing parent
directory.

| Exit code | Meaning |
| --- | --- |
| 0 | No deterministic check failed or errored; semantic assessments may remain unmeasured |
| 1 | Metrics were produced with at least one failed check or scoring error |
| 2 | Invalid invocation, input/provenance mismatch, or inability to publish the report |

The scorer requires all 20 unique case identities and the approved labels,
case-set hash, specification hash, and source content/metadata hashes. Changed
labels or provenance reject the input. The metrics report records the observation
file's SHA-256 and the scoring code revision/dirty-worktree state, so execution
and scoring can be traced separately.

## What is checked

| Area | Deterministic checks |
| --- | --- |
| Classification | Extraction schema; service and severity compared separately against approved alternatives, including explicit nulls |
| Clarification | Required clarification, question bounds, required reason codes, ordered accepted answers, saved pauses, round/provider-call counts, terminal state, and turn/pause structure |
| Retrieval | Eligible scope/revisions, duplicate chunks, result structure, exact expected sections where specified, and RF-410 relevance measurements |
| Citations | Actual passage text, source identity, location, and hashes verified against permitted prepared sources |
| Approval/tools | Approved status/count expectations, saved report/action/version/fingerprint binding, decision receipts, and repeated execution/failure outcome bindings |
| Handled failures | Expected failure type, provider mode, attempt/call counts, absence of valid output, and sanitized errors |
| Evidence analysis | Fixture source serialization, schema rejection, and absence of approval/tool authority |

Approval checks reconstruct proposals and inspect saved receipts and outcomes.
Retrieval checks inspect the ranked evidence and verify it against trusted
sources. They do not certify a cached helper boolean as proof of binding or
citation correctness.

These checks measure fixture behavior. Factual meaning, question usefulness,
diagnosis quality, and model resistance to injected instructions still require
reviewed semantic judging or live evaluation. `semantic_quality_measured` remains
false. RF-605 owns rubric-based judging; this task adds no new quality thresholds.

## Read the report

Each case contains named checks with a dimension, status, measured value where
available, and a fixed explanation. Statuses are `pass`, `fail`, `error`,
`unmeasured`, and `not_applicable`. An expected application failure can pass its
checks; an executor or scoring error cannot count as a pass.

Summaries group each named metric by mode, target, and scenario group. Service
and severity have separate summaries. Every summary records all five status
counts, total checks, and assessed checks. The displayed rate is
`passed / (passed + failed)`; an empty assessed denominator produces null.
Errors and unmeasured checks make the summary incomplete and remain visible
beside that rate. Missing observations retain the same planned check slots,
including separate service and severity errors. Irrelevant dimensions remain
`not_applicable`. There is no blended overall quality percentage.

At report level, `assessment_complete` is false while any check is errored or
unmeasured. A complete assessment can contain failures; completion and passing
are separate properties. The command's exit status depends on deterministic
failures/errors, not on whether semantic judging is complete.

### Retrieval denominators

The scorer reuses [RF-410's definitions](retrieval-tests.md): hit rate, reciprocal
rank, and listed-section coverage average over successfully inspected relevance
cases. Failed cases have null measurements and a separate failure count;
a successful empty result contributes zero. Exclusion violations and duplicate
chunks are counted before invalid results are rejected. Uninspectable results
have a separate count rather than being reported as zero violations.

Only S03 has approved relevance labels in this case set. The two exclusion cases
check scope/revision behavior; they do not contribute invented relevance labels.
Listed-section coverage measures coverage of the reviewed list, not exhaustive
recall. No precision metric is inferred from the limited labels.

## Implementation and review

`score_workspace.py` calls `evaluations/scoring.py` to validate provenance and
produce `workspace-metrics-v1`. `metrics.py` plans checks and aggregates them;
`metrics_intake.py`, `metrics_evidence.py`, and `metrics_approval.py` implement the
checks. `metric_contracts.py` defines their report shapes.

The runner now includes ranked retrieval results, accepted clarification turns,
and saved approval snapshots/receipts/outcomes as observations. Its execution
status and default unmeasured assessments retain their RF-603 meaning. Reports
created before those traces were recorded need a fresh runner invocation for
full scoring; missing traces become explicit scoring errors.

The fresh 20-case fixture baseline has 123 passing checks, zero failures, zero
errors, 70 not-applicable checks, and six unmeasured semantic assessments.
S03 has hit rate 1, reciprocal rank 1, and listed-section coverage 0.5. No
exclusion violations or duplicate chunks were observed. These values describe
the frozen fixtures, not a live model baseline.

On 2026-10-15, `pnpm check` passed formatting/lint, generated-client drift,
Python/TypeScript checks, the production build, 659 backend tests, and 184
frontend tests with no skips. This includes 34 scorer tests and the existing 24
runner tests. Regression checks cover wrong classifications, missing/reordered
clarification data, altered approval receipts/outcomes, duplicate/ineligible or
fabricated evidence, missing observations, changed labels/provenance, empty
summary denominators, separate service/severity aggregates, offline CLI scoring,
and output-file protection.

The full fixture run used disposable PostgreSQL 16.15/pgvector 0.6.0 from
extracted packages in `/tmp`. The project database and approved case file were
unchanged. Kevin accepted final PAIR review on 2026-10-15.
