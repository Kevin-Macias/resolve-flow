# Evaluation specification (RF-601)

Status: Kevin approved this specification in PAIR review on 2026-10-14.
RF-601 is DONE. It defines the contract for later cases, runner, and metrics.
Individual case labels, score thresholds, and live runs require their own review.

## What an evaluation tells us

An evaluation runs a fixed scenario and compares observed behavior with
expectations reviewed before the run. Unit tests establish individual code
rules; evaluation reports show how a versioned system performs across a
reviewed collection of scenarios. A schema-valid response can still be wrong.

For example, the existing [severity policy](severity-policy.md) says that urgency
alone does not establish impact. A case can specify that its report leaves
severity unknown, then check the extractor's actual classification. Returning
valid JSON with `critical` would still fail that expectation.

Kevin owns case labels, allowed alternatives, safety expectations, and metric
interpretation. Codex may draft proposals and implement agreed mechanics under
the [PAIR agreement](working-agreement.md#pair). Freeze expectations before
examining the evaluated outputs; record later corrections as a new case-set
version rather than changing labels to fit a result.

## Scope and execution modes

Evaluate the implemented boundaries separately:

| Target | Available behavior | Interpretation |
| --- | --- | --- |
| Extraction | Structured report extraction with model/settings, prompt version, typed failures, and bounded attempts | Classification and prose quality require observed model outputs; fixtures only verify the surrounding machinery |
| Clarification/intake | Policy decisions, bounded rounds, ordered answers, incomplete continuation, durable pause/resume | Scripted extraction responses can test transitions and limits without testing a model's question quality |
| Retrieval/citations | Scoped retrieval, version-bound evidence, citation checks, and claim assembly | Deterministic ranks test mechanics; provider rankings are needed for provider relevance measurements |
| Preliminary evidence analysis | Separate support analysis with claim-only output and verified references | Structural validity and reference provenance are testable; whether prose is justified needs semantic review |
| Approval/execution | Manually prepared exact-version proposal, explicit decision, guarded simulated tool | Observe decision/result binding and dispatch counts; the adapter creates no real ticket |

Every result declares the target and mode. Modes are `fixture` and
`live`, consistent with the existing retrieval evaluator. Fixture outputs are
scenario inputs, not evidence of model intelligence. The offline intake demo
script and fixture-ranked evidence must stay labeled as simulations.

Live execution is opt-in and requires a separate approved run scope. It may
call extraction, query embeddings, or evidence analysis only as explicitly
selected. The deferred RF-410 live retrieval baseline remains deferred. Ordinary
tests and evaluator development stay offline.

Customer summary confirmation, automatic retrieval/diagnosis orchestration,
automatic proposals, real tool writes, and full cost accounting remain outside
the implemented evaluation targets. Record their quality as unmeasured; do not
stitch disconnected components together and call that the production end-to-end
workflow. The hands-on platform checkpoint is separate.

## Case contract

RF-602 will author 20 scenarios: five straightforward, five ambiguous, five
adversarial, and five failure/safety cases. Each scenario has one primary group
for counting and may carry additional tags. Kevin reviews the actual scenarios
and expected outcomes before implementation uses them as ground truth.

| Field | Required meaning |
| --- | --- |
| Identity | Stable case ID, case-set version, primary group, target, and purpose |
| Input | Exact report/query and any ordered clarification answers needed for this target |
| Trusted context | Explicit simulated identity/account grants, service catalog, report/run state, and permitted corpus revisions as applicable; permissions come from application setup |
| Scenario setup | Initial state and explicit requests/decision sequence; fixture provider responses or injected failures when testing mechanics |
| Expectations | Reviewed expected classifications, clarification behavior, fact/evidence constraints, allowed tool behavior, and expected terminal or failure state |
| Applicability | Which checks apply to this target and mode, with a reason for omitted checks |
| Provenance | Source policy references and reviewer approval/version for the labels |

An expected `null` is an explicit unknown classification, not an omitted
expectation. Where multiple answers are defensible, record a reviewed nonempty
set of allowed values and explain why. Do not silently add alternatives after
a mismatch. Different targets may share a scenario but retain separate results.

Do not construct a fake provider by reading the expected result at runtime and
then report its output as measured model quality. Keep fixture responses and
expected application behavior explicit, so a transition or validation bug can
still cause the case to fail.

## Expected behavior and measurements

The policies below already exist. The evaluation contract records
which case-specific expectations make them measurable; it does not change them.

| Area | Expected behavior to label | Deterministic checks and limits |
| --- | --- | --- |
| Service and severity | Allowed service codes and tentative severity, including explicit unknowns, following extraction/severity policy | Exact membership in reviewed allowed values; report service and severity separately |
| Clarification | Whether a gap exists, expected reason categories, allowed question count, round limit, and answer/incomplete-continuation transitions | Compare policy decisions, bounds, and transitions; useful question meaning is a later rubric/human judgment, not exact text equality |
| Reported facts | Required observations, contradictions, missing information, and unsupported conclusions that must not be asserted | Structural checks can verify fields and preserved fixture values; paraphrase fidelity and invented semantic claims require reviewed semantic assessment |
| Evidence | Eligible revisions and acceptable passages, required provenance, and whether any relevant evidence is expected | Reuse RF-410 hit@5, reciprocal rank, listed-alternative coverage, and exclusion/duplicate counts where applicable; labels are not exhaustive relevance judgments |
| Citations and analysis | References resolve to authorized supplied evidence with correct revision, hashes, location, and excerpt; supported/inference/gap/conflict labels retain their meanings | Verify reference integrity mechanically; a valid citation does not prove a claim follows from its passage |
| Tools and approval | Whether dispatch is permitted after the declared sequence; exact saved proposal/version/fingerprint, first decision, and expected simulated outcome or unknown result | Compare saved decisions, adapter dispatch observations, and results; rejection, stale bindings, duplicates, and unconfirmed execution reuse the reviewed RF-309/RF-508 expectations |
| Failures and isolation | Expected typed refusal/provider/validation failure and customer/support projections within the declared access context | Check bounded attempts and sanitized outcomes; an expected handled failure can be a passing case if the required behavior is observed |

RF-604 implements agreed deterministic measurements. RF-605 defines subjective
rubrics and judge settings separately. Until that work is reviewed, semantic
checks are explicitly unmeasured or recorded as Kevin's manual assessment;
substring matching must not masquerade as factuality or groundedness scoring.

## Results, failures, and denominators

Per-check statuses are `pass`, `fail`, `error`, `unmeasured`, and
`not_applicable`. `fail` means observed behavior violated its expectation.
`error` means the evaluator could not establish the result, such as broken
setup or an unexpected infrastructure failure. A deliberately injected timeout
that is handled as expected is not an evaluator error.

Show counts for every status and the applicable denominator next to each metric.
A pass rate uses assessed checks (`pass + fail`); an empty denominator is null.
Errors and unmeasured applicable checks make the assessment incomplete even
when every assessed check passes. Report group/target/mode results separately;
do not turn fixture successes into a live quality average or a single blended
score that hides policy failures.

Reuse RF-410's established retrieval failure and denominator semantics when
including its results. A successful empty search differs from a failed search.
Observed exclusion counts are incomplete when a result could not be inspected.
Do not invent precision from the existing non-exhaustive relevance labels.

Keep existing hard access and exact-approval requirements visible as violations,
independently of quality averages. Proposed quality thresholds and experiment
success criteria need Kevin's review after a baseline; RF-601 sets none.

## Reproducibility and report boundaries

Record case/spec versions, code revision and whether the worktree is dirty,
target/mode, timestamp, fixture or provider configuration, model and prompt
ID/version, corpus hashes/revisions, embedding/chunking settings, expected and
observed results, failures, and measurement applicability. Record attempts and
returned usage when available; missing duration/cost remains unavailable rather
than zero. These are evaluation artifacts, not a replacement for RF-705.

Use fictional inputs and test identities. Reports must not serialize credentials,
raw provider exceptions, or unauthorized passages. Error information stays
sanitized as in existing application contracts. Retain enough permitted output
to inspect a failed classification or semantic claim. Repeat comparisons on the
same reviewed cases and corpus, disclosing changes in settings and versions.

## Review and completion

Kevin approved these choices on 2026-10-14:

1. Start with separate implemented targets and explicitly separate fixture and
   live results, keeping live runs opt-in.
2. Use reviewed case expectations, deterministic structural/transition checks,
   and separately identified semantic assessment; defer subjective rubrics to
   RF-605 and numeric quality thresholds until a baseline is reviewed.
3. Use the case/result fields and incomplete-assessment rules above as the
   contract for RF-602–604, including the planned 20-case group balance.

RF-601 is DONE after this review. The interpretation distinguishes three
outcomes: a deliberately injected timeout handled correctly can pass; a broken
evaluator setup is an error; an unjustified model classification fails its
expectation even when its JSON is valid. RF-602 owns the actual reviewed cases;
RF-603 owns the repeatable runner. Documentation links, whitespace, and the
single NEXT ticket were checked. This ticket adds no evaluator code or provider
call.

Related contracts: [extraction](extraction-contract.md),
[severity](severity-policy.md), [clarification](clarification-policy.md),
[retrieval evaluation](retrieval-tests.md), [citations](citations.md),
[document injection](document-injection.md),
[support evidence](evidence-panel.md),
[approval edge cases](approval-edge-cases.md),
[support approval](support-approval-controls.md), and
[metrics limitations](execution-metrics-ui.md).
