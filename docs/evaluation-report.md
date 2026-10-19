# Workspace evaluation report (RF-606)

Status: implemented and verified under DELEGATE ownership on 2026-10-15.
RF-606 is DONE.
The command turns existing observation, metric, and optional judgment artifacts
into standalone Markdown. It runs offline without a database or provider calls.

## Generate a report

From the repository root, use files produced by the
[runner](evaluation-runner.md), [deterministic scorer](deterministic-metrics.md),
and optionally the [rubric judge](rubric-judging.md):

```bash
uv run --directory apps/api python scripts/report_workspace.py \
  --observations /tmp/resolveflow-workspace-observations.json \
  --metrics /tmp/resolveflow-workspace-metrics.json \
  --judgments /tmp/resolveflow-workspace-judgments.json \
  --output /tmp/resolveflow-workspace-report.md
```

Omit `--judgments` when no semantic assessment exists. The report then says
semantic quality remains unmeasured. Omit `--output` to print Markdown to stdout.
An output file must be new and its parent directory must exist. Input artifacts
are read without modification.

| Exit code | Meaning |
| --- | --- |
| 0 | Report produced without current deterministic or effective judge failures/errors; assessments may remain unmeasured |
| 1 | Report produced with current failures/errors |
| 2 | Invalid invocation, inconsistent/incompatible inputs, or inability to publish the report |

A successfully generated report is not a quality pass. Its first section states
the candidate mode, execution outcomes, and separate deterministic/judge status
counts. An expected handled failure can pass its checks; an executor error
remains an error. No live candidate quality is inferred from fixture outputs.

## Read the sections

The deterministic table reports each named metric by target and scenario group,
with pass/fail/error/unmeasured/not-applicable counts, assessed and total check
counts, the conditional pass rate, and an incomplete flag. Empty assessed
denominators are null. Service and severity remain separate. A classification
table shows approved alternatives beside observed values, distinguishing explicit
unknowns from unavailable observations.

Failures and scoring errors are listed by case, target, dimension, and check.
Evidence and tool failures remain visible individually regardless of averages.
Retrieval hit/rank/listed-section coverage retain RF-410's successful-case
denominators, with failed and uninspected cases counted separately. The current
case set has relevance labels only for S03; the report invents no precision or
exhaustive recall measurement.

Semantic assessments have their own table and per-criterion explanations,
references, judge attempts/usage, and resolved model identifiers. The offline
fixture judge leaves quality unmeasured. Model verdicts are subjective opinions;
the report does not establish human calibration. Variable text is escaped as
literal Markdown content, including HTML/link syntax in model explanations.

Provenance sections retain artifact hashes, candidate/scoring/judging revisions
and dirty-worktree flags, case/specification hashes, corpus revision/content/
metadata hashes, known candidate settings, extraction call settings/usage, and
judge model/prompt/rubric details. Configuration values are limited to known
scalar fields; arbitrary configuration dictionaries and raw observations/passages
are not dumped. Missing usage, resolved versions, duration, and cost stay
unavailable. A dirty revision alone cannot reproduce uncommitted code.

## Compare a baseline

Add the matching baseline observation and metric files, and its judgment file
when available:

```bash
uv run --directory apps/api python scripts/report_workspace.py \
  --observations /tmp/resolveflow-workspace-observations.json \
  --metrics /tmp/resolveflow-workspace-metrics.json \
  --judgments /tmp/resolveflow-workspace-judgments.json \
  --baseline-observations /tmp/resolveflow-baseline-observations.json \
  --baseline-metrics /tmp/resolveflow-baseline-metrics.json \
  --baseline-judgments /tmp/resolveflow-baseline-judgments.json \
  --output /tmp/resolveflow-workspace-comparison.md
```

Without a baseline, regressions and improvement are explicitly unassessed.
Comparing the same observation bytes is labeled a comparison control, not a new
candidate experiment.

For each case/metric, pass to fail is a regression and fail to pass is an
improvement. Moving an assessed check to error/unmeasured is lost assessment,
not an improved denominator. Applicability changes and newly assessed checks
are labeled separately. Unchanged statuses produce no change row; the full
current metrics and baseline counts/provenance remain visible. Configuration
changes and code revisions are disclosed without attributing causality.

Retrieval quality deltas require the same nonempty set of successfully inspected
relevance cases. A changed successful cohort shows both values but no comparable
quality delta. Failure and uninspected counts remain separate.

Semantic quality comparisons require model judgments on both sides with the
same method, rubric, prompt, provider settings, timeout/attempt settings, and
known matching resolved model versions. Missing judgments, fixture judges,
changed protocols, or unresolved/changed model versions produce an explicit
comparison limitation. Deterministic comparison still runs. The tool adds no
aggregate quality threshold or experiment success criterion; RF-607 owns the
reviewed improvement experiment.

## Validate the inputs

Both runs must bind to the approved current case set, specification, and local
source snapshot. Observation bytes must match the hashes in their score and
judgment artifacts. The reporter recomputes deterministic checks offline to
verify the supplied metric artifact against the current `workspace-metrics-v1`
contract. It retains the supplied artifact and its scoring provenance; it does
not replace historical scores. If the retained scores no longer satisfy that
contract, use a compatible code checkout or explicitly rescore for a reviewed
comparison, keeping the historical artifact.

Judgments must cover the six approved extraction cases with the right group,
method, input hash, criterion slots, applicability, verdicts, and references.
Effective statuses and summaries must agree with those verdicts; fixture verdicts
cannot become measured passes. Fixed mechanical error explanations are checked,
and subjective explanations must match the retained model verdict. Inconsistent
inputs reject the report before publishing output, with a fixed safe error
message rather than artifact contents or raw exceptions.

`evaluations/report_inputs.py` validates the bundle, `report_comparison.py`
classifies compatible transitions, and `reporting.py` renders Markdown.
`scripts/report_workspace.py` supplies the CLI. Application endpoints, runtime
policy, approved labels, and existing JSON report formats are unchanged.


## Verification

On 2026-10-15, `pnpm check` passed formatting/lint, generated-client drift,
Python/TypeScript checks, the production build, all 732 backend tests, and all
184 frontend tests with no skips. The 34 new reporting tests also passed
separately. They cover mismatched/altered artifacts, missing judgments, explicit
executor errors, null denominators, deterministic and semantic regressions,
lost assessment, retrieval cohort changes, changed/unresolved judge versions,
literal rendering of model explanations, configuration projection, offline CLI
behavior, safe errors, and output-file protection.

The standalone report generated from the complete 20-case fixture observations
shows 123 passing deterministic checks, zero failures/errors, six unmeasured
semantic placeholders, and 70 not-applicable checks. The separate offline judge
has 15 unmeasured checks and three not-applicable question checks. A comparison
against the same artifacts has no status changes and is explicitly a control.
These generated reports validate reporting behavior; they are not an improvement
experiment or a live quality baseline.

Full backend checks used a dedicated Docker pgvector/PostgreSQL 17 container
without a volume. Its evaluation schemas were cleaned up and the container was
removed afterward. The project database, application containers, and approved
case file were unchanged. RF-607 owns the next reviewed improvement experiment.
