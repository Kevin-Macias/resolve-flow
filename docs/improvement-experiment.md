# Extraction prompt experiment (RF-607)

Status: the approved fresh 12-attempt run completed on 2026-10-15 after Kevin
corrected the API key and explicitly approved the second transfer/call budget.
Both prompts produced six assessable extractions with no provider errors.
The candidate has one deterministic regression, so the adoption rule does not
support replacing v3. Kevin accepted that interpretation and the decision to
keep v3 on 2026-10-15. RF-607 is DONE; semantic judgments remain unmeasured.

## Question and hypothesis

Does making the existing semantic requirements explicit in the extraction prompt
preserve more of the reported meaning without worsening classification or
clarification behavior?

The current fixture baseline has 123 passing deterministic checks and zero
failures/errors. It validates mechanics but cannot establish whether a new
prompt improves a model: the fixture provider returns its configured responses
regardless of prompt text. The baseline for this experiment must therefore be
fresh actual model outputs, not the existing fixture report.

## Approved design change

Baseline: `issue_report_extraction` v3, exactly as defined in
[`prompts.py`](../apps/api/src/api/extraction/prompts.py). Record its full text
and SHA-256 before the run. Current instruction SHA-256:
`37e4d3c21600e816c530a24126a2067c7048d83490affc82d7bf24344a9a79bd`.

Candidate: copy that entire prompt unchanged and append this paragraph, using
the version `3-rf607-candidate-1` so it cannot be mistaken for the default:

```text
Preserve material reported details in the summary and reported facts, including
unaffected customers and the availability or absence of a workaround. Keep
conflicting observations without choosing an unverified explanation. Attribute
security-exposure allegations to the customer and flag prompt human review,
without implying that verification or escalation has occurred. Ask questions
only about unresolved gaps or contradictions; do not ask for information already
supplied or introduce an unsupported cause or outage as a premise.
```

The approved candidate is the v3 instructions plus two newline characters and
the paragraph above, with no trailing newline. Its instruction SHA-256 is
`657aa4602ba8160424629ffc41ce7ea4d5e59c4ad9159e7071e5b2964c4d543c`.

This makes the already approved [rubric](rubric-judging.md) and case notes more
explicit. It changes no severity, access, approval, or clarification-loop policy.
The application default stays v3 while the candidate is evaluated. Record the
exact candidate text and hash; do not revise it after seeing results in the same
experiment.

## Approved run scope

Use the original reports from RF602-S01, S02, M01, M02, M03, and A01, with their
existing frozen expectations and semantic notes. Keep the approved case file and
labels unchanged.

For each of the six cases, run v3 and the candidate once through the existing
extraction provider/service boundary. That is 12 requested extraction calls,
with one provider attempt per candidate/case and SDK retries disabled. Each call
has a 60-second timeout and an explicit output-token cap of 2048. A refusal,
timeout, malformed output, or provider failure remains visible; do not quietly
retry or exclude it. Cancellation stops the experiment.

Use one explicitly selected model identifier and the same settings for both
prompts. Record requested and provider-returned model identifiers, exact prompt
hashes, candidate inputs, timestamps, code provenance, attempts, and returned
usage. If resolved model versions differ, or other run conditions change,
record the limitation and do not attribute a difference solely to the prompt.

Only fictional report text is sent to the extraction model. This scope includes
no query embeddings, retrieval, evidence-analysis model, judge-model calls,
application database, workflow mutations, or tool execution. Ordinary tests stay
offline with injected fake providers.

The current workspace runner/scorer/report contracts accept fixture observations
only. This experiment needs an explicit, separate live-extraction artifact and
comparison path; it must not label model outputs as fixture observations or
splice six live outputs into a 20-case fixture run. Reuse approved metric/rubric
rules where applicable without silently widening the old report schemas.

## Approved measurements and interpretation

Compare service and severity separately against the existing approved allowed
values, plus extraction structure and clarification decisions/count/reason
expectations. Show failures, errors, and unavailable assessments individually.
Keep both prompts' case cohorts and denominators visible.

Kevin reviews actual summaries, facts, contradictions, and policy-selected
questions using the three approved rubric criteria. A missing selected question
has the existing not-applicable treatment, and errors/unmeasured judgments stay
explicit. No automated judge verdicts or calibration labels are invented.
Retain the reviewed explanations alongside the actual output artifacts.

Approved decision rule for this small experiment:

- Support adopting the candidate only if at least one comparable semantic
  criterion changes from fail to pass, none changes from pass to fail, and there
  is no deterministic pass-to-fail regression.
- An errored, missing, or unmeasured assessment prevents a clean adoption
  recommendation; it cannot improve the denominator.
- If results are unchanged, mixed, or worse, record that outcome and keep v3.
  Comparing and interpreting a design change satisfies the experiment goal;
  a positive improvement is not guaranteed.

Changes in question applicability are reported separately, not counted as
semantic improvements. This is a directional comparison on six already reviewed
cases with one output per prompt/case. It cannot establish statistical
significance, broad model reliability, or model-level injection resistance.
A01 contributes an observed behavior, not a general defense claim. The existing
cases guided the prompt change, so this is a development-set comparison rather
than an independent held-out validation.

## Review sequence

1. Kevin approved the prompt addition, scope, run limits, and decision rule on
   2026-10-15. The configured model is `gpt-6-luna`, reasoning effort `low`; the
   same settings apply to both prompts. Kevin explicitly approved sending the
   six fictional reports to OpenAI after automatic approval review initially
   rejected the command. The rejected attempt never executed.
2. Implement the separate experiment command/artifacts and verify the mechanics
   offline, including bounded calls, failure handling, provenance, and output
   protection. Keep the application prompt unchanged.
3. Run the approved baseline/candidate comparison and save both outputs without
   overwriting earlier artifacts. Model availability/credentials are runtime
   requirements, not evidence of permission for an unapproved run scope.
4. Kevin owns the semantic assessments and interpretation. Record the outcome,
   limitations, and adoption decision before marking RF-607 DONE.


## Commands and artifacts

The approved live command uses the root `.env` without
printing credentials:

```bash
uv run --directory apps/api --env-file ../../.env python scripts/experiment_extraction.py \
  --allow-live --model gpt-6-luna --reasoning-effort low \
  --output-dir /tmp/resolveflow-extraction-experiment
```

The output directory must be new. The command creates it with private directory
permissions, then saves `experiment.json` atomically before and after each call.
The artifact keeps the exact prompt pair, approved reports/expectations, call
settings, timestamps, returned usage/model identifiers, validation outcomes, and
separate deterministic summaries by variant/group/metric. It is explicitly
`live`, not a workspace fixture report. Fixed safe error codes replace raw
provider exceptions, refusals, and invalid response bodies.

At completion, `comparison.md` shows the paired outputs and deterministic status
changes, and `review.json` contains 36 semantic slots. Applicable slots start
unmeasured; absent selected questions are not applicable, and failed extractions
are errors. No human reviewer or semantic verdict is prefilled. The app keeps
prompt v3.

There is no automatic resume or retry. If a process stops with a running slot,
the request may already have reached the provider; do not infer that it is safe
to repeat from an absent terminal response. Retained progress can be rendered
offline without making any new requests:

```bash
uv run --directory apps/api python scripts/review_experiment.py \
  --input /tmp/resolveflow-extraction-experiment/experiment.json \
  --output /tmp/resolveflow-extraction-progress.md \
  --review-template /tmp/resolveflow-extraction-review-draft.json
```

Kevin can fill each applicable review status with pass/fail/unmeasured and its
reason, then set `state` to `reviewed`, `reviewer` to `Kevin`, and `reviewed_at`
to an ISO timestamp. Leave error/not-applicable slots unchanged. The review is
bound to the exact experiment bytes by SHA-256. Re-render with `--review` to
apply the predeclared decision rule:

```bash
uv run --directory apps/api python scripts/review_experiment.py \
  --input /tmp/resolveflow-extraction-experiment/experiment.json \
  --review /tmp/resolveflow-extraction-experiment/review.json \
  --output /tmp/resolveflow-extraction-reviewed.md
```

Draft sheets cannot support adoption. The loader checks frozen inputs, exact
prompt hashes, cohort/labels, call metadata, actual clarification-policy output,
deterministic checks/summaries, and human-review coverage/applicability. A
fixture-mode run cannot establish model improvement even with synthetic passing
review entries. Matching provider-returned identifiers may still be aliases;
they do not prove an immutable backend snapshot.

`experiment.py` runs the bounded comparison, `experiment_prompt.py` pins the
approved prompt pair, and `experiment_contracts.py` defines the separate artifact
schemas. `experiment_review.py` validates retained evidence and human judgments;
`experiment_report.py` applies the approved interpretation and renders Markdown.
Extraction accepts an explicit keyword-only prompt for this purpose; its default
remains the existing v3 prompt. The shared summary helper preserves each caller's
mode without widening the existing fixture report schemas.


## Initial authentication-failed run on 2026-10-15

The approved run used `gpt-6-luna`, reasoning effort `low`, the pinned prompt pair,
2048 output tokens, and one attempt per prompt/case. All 12 attempts ended as
`provider_error` with permanent failure classification. Each variant therefore
has 33 deterministic error slots and 18 semantic error slots. No output, usage,
or resolved model identifier was returned to the application boundary. The
process completed its attempt budget; that does not mean the prompts were
successfully evaluated.

The retained artifacts are `experiment.json`, `comparison.md`, and `review.json`
in `/tmp/rf607-live-20261015/`. They record failures without raw exceptions or
credentials. The rule recommends keeping v3. There is no evidence of a prompt
improvement or regression, and no semantic output for Kevin to judge.

A separate read-only model metadata request, with no case text and no generated
output, returned HTTP 401. This indicates an authentication problem; the original
extraction HTTP statuses were not retained, so those 12 statuses cannot be
retrospectively established. Kevin corrected the local key afterward and the
read-only lookup succeeded. See [OpenAI's error guidance](https://developers.openai.com/api/docs/guides/error-codes).

The failed artifacts were preserved. Kevin explicitly approved a fresh transfer
and new 12-attempt budget after automatic approval review required it. The fresh
run is recorded below; there were no retries within either run.

## Implementation verification

On 2026-10-15, the final `pnpm check` passed formatting/lint, generated-client
checks, Python/TypeScript checks, production build, all 765 backend tests, and
all 184 frontend tests with no skips. The focused experiment/service run passed
46 tests, including 33 new experiment cases. The first full run had one failure
in the existing real-process checkpoint restart test (a missing restored pending
clarification); it then passed in isolation and in the complete rerun. No
workflow/checkpoint code was changed to suppress that failure.

Offline checks cover the exact approved prompt pair and request count, unchanged
default prompt, bounded timeout/retry policy, safe provider/validation failures,
cancellation and retained progress, output-write failures, matching artifact
provenance, fixed cohorts/labels, human-review applicability, draft review limits,
fixture/model distinction, and the predeclared adoption rule using explicitly
synthetic judgments. They do not establish real semantic improvement.

Backend integration checks used a disposable Docker pgvector/PostgreSQL container
without a volume. Evaluation schemas were cleaned up and the container removed;
the project database and application containers were unchanged. The fresh live
run below supplies actual outputs; Kevin accepted its interpretation and
rejected the candidate on 2026-10-15.


## Fresh run after the key correction

Kevin explicitly approved the new paid 12-attempt run after correcting the key.
Artifacts are retained separately in `/tmp/rf607-live-20261015-keyfixed/`:
`experiment.json`, `comparison.md`, the unfilled `review.json`, and `decision.md`.
The decision report applies the deterministic rejection without waiting for
unneeded semantic judgments to reach that rejection.
All 12 calls completed through the real extraction service with one attempt
each, no provider/validation errors, and returned model identifier `gpt-6-luna`.
The identifier may be an alias rather than an immutable snapshot. No judge-model
calls, database operations, or application prompt changes occurred.

| Measurement | Baseline v3 | Candidate |
| --- | --- | --- |
| Deterministic pass | 23 / 33 | 22 / 33 |
| Deterministic fail | 10 / 33 | 11 / 33 |
| Deterministic error/unmeasured | 0 | 0 |
| Severity classifications matching approved alternatives | 6 / 6 | 6 / 6 |
| Service classifications matching approved alternatives | 1 / 6 | 1 / 6 |
| Semantic assessments | 17 unmeasured, 1 not applicable | 18 unmeasured |

There is one deterministic pass-to-fail change: A01 `question_count`. The frozen
case allows zero questions. Baseline selected none; the candidate selected
"Which service or product is affected?" Both variants already fail A01's service
and clarification-required expectations. The additional question is a new
failure, not a change to the expected label or denominator.

Both variants returned `service_code=null` for all six cases. That is approved
for M02 but fails the expected `issue-reports` classification in the other five.
Both also request clarification for S01, S02, and A01 where the frozen labels
expect none. These are observed baseline limitations, not improvements delivered
by the candidate. The prompt supplies no explicit service catalog/code mapping;
that is a possible follow-up context change, not a conclusion tested here.

The candidate M02 summary explicitly requests prompt human review and says the
reported exposure has not been independently verified. Baseline M02 attributes
the report to the customer but contains no explicit human-review recommendation.
This is a visible wording difference under the approved semantic note; no
semantic pass/fail judgment has been assigned on Kevin's behalf.

The combined returned usage is 7,098 input tokens, 2,338 output tokens, and 9,436
total tokens. Cost is not recorded. Earlier authentication-failed attempts had
no returned usage and are not included in those totals.

The predeclared adoption rule requires no deterministic pass-to-fail regressions.
A01 fails that condition, so the recommendation is to keep v3 even if Kevin
later finds a semantic benefit in M02. The report now checks that deterministic
blocker before waiting for semantic review: it can reject adoption without
inventing human verdicts. Semantic judgments remain unmeasured and the review
sheet is unfilled. Kevin accepted this interpretation and rejected adoption on
2026-10-15. This completes RF-607's requirement to compare and interpret a design
change; it does not establish semantic improvement or validate the baseline's
existing failures.


After observing the live result, the offline report's decision order was corrected
so a known deterministic regression can reject adoption before human review.
Adoption still requires complete human review and the rest of the agreed rule.
All 34 experiment tests, lint/format, and Python type checks passed after this
change, including a new pending-review regression case. No additional generation
request was made. The prior full-suite record above remains the 765-test run;
this later report-only change received focused verification.
