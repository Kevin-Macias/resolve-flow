# Support approval controls (RF-508)

Status: Kevin approved the HTTP/orchestration contract and mutation access on
2026-10-13. Implementation and verification are complete; Kevin accepted final
PAIR review on the same date. RF-508 is DONE.
RF-507's approved card, inline confirmations, accessibility, and outcome wording
remain the UI contract. This document defines the missing backend integration.

## Approved entry into approval

Support explicitly authors a simulated `create_ticket` proposal after a saved
customer intake reaches `needs_confirmation`, with no pending intake operation.
The form supplies title, description, nullable service code, nullable tentative
severity, and explanation. These are human-authored draft ticket fields, not
assertions that the customer confirmed a summary or that a model verified a cause.

Customer summary confirmation is still missing. The approved scope therefore
labels this as a separate support simulation over unconfirmed observations.
Kevin approved changing the original orchestration prerequisite in
`action-approval.md`. This does not complete the product's customer-confirmation
step or automatically propose an action from extraction/evidence output.

The server sets report ID, tool, action ID, version, idempotency key, expected
simulated effect, and low risk with the application-owned reason that the adapter
performs no ticket write. Risk remains separate from tentative incident severity.
The complete saved proposal is read-only during the decision interaction.

Use the existing intake UUID as the workflow identity and its separate
`<run UUID>:approval` checkpoint thread. A durable registry binds report, owning
account, intake run, proposal operation, saved proposal/input fingerprint, and
initialization state before starting the approval graph. One approval path per
intake is supported. A decided path cannot be revised or replaced in this scope.

## HTTP operations

| Operation | Behavior |
| --- | --- |
| `GET /support/issue-reports/{report_id}/action` | Read saved proposal, decision receipt, execution result/failure, initialization state, and approval events; return an explicit absent state when no proposal exists |
| `POST /support/issue-reports/{report_id}/proposal` | Create or revise an undecided proposal and persist a fresh review interrupt; never approve or execute it |
| `POST /support/issue-reports/{report_id}/runs/{run_id}/decision` | Submit the existing four-field `ApprovalReply` through `ApprovalRunner`; return the actual saved outcome |

The proposal body contains an operation UUID, the expected current proposal
fingerprint (null only for creation), and the human-authored fields above.
Identical UUID/payload replay reuses the saved preparation; UUID reuse with changed
fields conflicts. The server uses the existing proposal factories. Before a
decision, a revision preserves action identity, increments version, creates a new
idempotency key, and establishes a new interrupt. A stale revision request conflicts.

The decision body contains only `action_id`, `version`, `fingerprint`, and
`decision`. The server resolves report/run/approval-thread bindings independently
of client input. Actor and decision timestamp come from current authentication and
application code. Unsupported fields, including replacement arguments or actor
IDs, are rejected.

The closed, versioned read response exposes the complete saved proposal and its
fingerprint, decision receipt, simulated result or sanitized unknown outcome,
and persisted approval events. Display status is derived from validated saved
state, never from the last clicked button. Original intake events remain in their
own endpoint; the page presents intake before approval and retains each stage's
saved sequence, IDs, and timestamps. No raw checkpoint or resume payload is exposed.

GET never initializes a stage, resumes execution, or reconciles an interrupted
write. It authenticates before inspecting checkpoints and rechecks access before
returning. It works independently of model/evidence-provider configuration.

## Approved access and freshness rules

Extend the explicit support account grants to proposal creation, revision,
decision, and the immediate simulated execution authorized by approval. Require
current support identity and report-account access at each boundary. The grants'
read permissions alone did not authorize these mutations; Kevin explicitly
approved extending the grant policy to these operations.

Saved outcomes for archived reports remain readable within current grants. New
proposals, revisions, and undecided actions on archived reports are blocked.
A replay of an already saved decision may return its outcome without executing.

Capture the proposal's source description, service, intake identity/revision,
and accepted clarification history in an input fingerprint. Before accepting a
new decision, reject changed observations or report state that requires fresh
review. Support must save a new proposal version rather than silently approve
an outdated context. After a decision, later observation changes do not rewrite
the receipt or result, and duplicate submissions cannot trigger execution again.

Immediately before simulated execution, recheck role, grants, report ownership,
archival state, and the approved input binding. If access/context has changed,
preserve any committed approval without claiming execution. Never infer current
permissions from checkpoint data or the proposal's risk label.

## Concurrency and interruption

Creation, revision, and decisions use the same PostgreSQL approval run lock and
checkpoint namespace as `ApprovalRunner`. Preparation also serializes the report
binding with intake operations, using a consistent report-then-run lock order.
Only undecided stages can receive a fresh proposal input/review interrupt.

The first committed decision wins. Opposite or duplicate replies with the correct
proposal binding return the saved outcome, including rejection or an unknown
execution outcome. Stale IDs, versions, fingerprints, and report/run mismatches
fail before dispatch. Changing any review content invalidates previous approval.

Proposal registry writes and graph checkpoints are separate commits. A failed
or interrupted preparation remains visible as preparing/unavailable, without
decision controls. Explicit replay of the same preparation operation may finish
initialization only after verifying no decision or execution exists; GET does
not repair it. This preparation replay must not resume an approved execution.

If observations change during interrupted preparation, explicit replay can finish
the old review interrupt on an eligible active report. The result is marked stale
and cannot be decided until support saves a new reviewed version. Archived reports
cannot finish preparation. The read response includes the accepted preparation
body so an authorized reviewer can replay it after a browser or worker restart.

Approval with no execution result remains approved but unconfirmed. Tool failure
retains the approval receipt and an unknown outcome. Neither refresh, reconnect,
duplicate approval, nor proposal replay retries execution. Reconciliation and real
effect idempotency remain RF-703. The only injected adapter is the existing pure,
deterministic simulation: no persisted support ticket and no external write.

## Errors and browser behavior

Use safe errors: 401 for missing/revoked identity, 403 for non-support role, 404
for unknown/ungranted report or mismatched report/run, 409 for stale input/proposal,
wrong lifecycle, or undecided actions on archived reports, 422 for invalid bodies,
and 503 for infrastructure or invalid saved state. Do not echo private failures.

Use generated types and shared Zod validation. Proposal creation/revision and
approval submission are explicit mutations with no automatic retries. Preserve
an uncertain proposal operation UUID until its saved outcome is established.

Keep RF-507's entire action card visible during inline confirmation. Pin it to
run/action/version/fingerprint, close it on any changed binding, transient read
failure, disconnect, or access loss, and require a fresh review. Reconnect/focus
refreshes saved state only. A network or uncertain decision error disables choices
until a successful saved-state read. A stale conflict refreshes the proposal and
requires a new confirmation. Access loss clears protected data across the support
page; old report/session callbacks cannot restore it. Never optimistically show
approval or ticket creation.

## Verification and review

Reuse the reviewed RF-309 expectations: first decision wins, stale bindings fail,
rejection never executes, duplicates never repeat execution, and unknown outcomes
require review. Add database-backed HTTP tests for report/run/account binding,
archival rules, fresh authorization at decision/execution/read time, proposal
revision, preparation replay after interruption, and restart restoration.

Frontend tests cover the full saved card, explicit null classification, keyboard
focus, both confirmations/cancellation, changed proposals, concurrent reviewers,
duplicate submissions, uncertain responses, disconnected/stale reads, saved
receipt versus execution, and session/report/access isolation. Verify real HTTP,
PostgreSQL checkpoints, reload/API restart, and desktop/mobile in the production
browser. No live model calls or external ticket writes are needed.

Implementation checks passed, and Kevin accepted final PAIR review on
2026-10-13. Kevin retains the authorization, approval, lifecycle, and important
edge-case decisions.

## Setup and code map

Apply Alembic migration `0005` and run the existing checkpoint setup command
before preparing actions. The migration adds `support_action_runs` and
`proposal_preparations`; proposal history and decision/execution state live in
PostgreSQL checkpoints. No model configuration is required for these endpoints.

From the repository root, with your local database configured:

```bash
nvm use
uv run --directory apps/api --env-file ../../.env alembic upgrade head
pnpm setup:checkpoints
```

`api/support/actions.py` owns authorization, input binding, replay, and guarded
stage orchestration. `action_models.py`, `action_schemas.py`, and `action_router.py`
define storage and the closed HTTP boundary. The app lifespan installs the service
alongside the existing support readers. Its tool is request-scoped, so call history
does not accumulate in app state.

`apps/web/src/features/approval/` separates the query/action hook, shared Zod
contracts, proposal authoring form, exact saved card, and inline decision controls.
The support page removes all protected sections when any of its reads establishes
access loss. Approval events follow intake events without renumbering either stage.

## Verification on 2026-10-13

Root `pnpm check` passed **585 backend and 152 frontend tests**, with no skips,
against disposable PostgreSQL 16 and pgvector 0.6.0. Formatting, lint, strict
Python/TypeScript checks, generated-client drift, and production build passed.
Migration upgrade, rollback, re-upgrade, and `alembic check` passed. Docker was
unavailable; the configured PostgreSQL 17 / pgvector 0.8.7 stack was not exercised.
The project database was not changed.

The 22 new backend tests cover HTTP grants, report/run binding, lifecycle and
archival rules, revision/UUID reuse, concurrent reviewers, corrupted saved data,
revocation after approval but before execution, tool failure, and interruption
on both sides of the preparation checkpoint commit. Replaying stale preparation
can establish a review but cannot authorize execution without a new version.

The 32 new frontend tests cover the full card, nullable classification, both
confirmations and focus/cancellation, exact decision bodies, duplicate submissions,
another reviewer's saved outcome, changed proposals, uncertain preparation/decision
requests, disconnect/reconnect, validation, stale reads, saved execution states,
and report/session/access isolation. The combined-page test verifies removal of
timeline, evidence, and action data together on action access loss.

Chromium used the production build, real HTTP, and persisted PostgreSQL checkpoints,
without HTTP interception. Manual proposal creation, approval/rejection, two
reviewers and stale versions, focus/cancellation, null classification, reload,
desktop/mobile long text, incomplete intake, foreign reports, archival, and revoked
roles passed. An injected deterministic simulation adapter paused after approval
was durably committed; the temporary API process was killed and restarted. The
saved approval returned as execution unconfirmed, and decision/preparation replay
and refresh did not dispatch the adapter again. Completed simulation results also
survived restart unchanged. No runtime browser errors, model calls, or real ticket
writes occurred. A screenshot review led to clearer argument spacing; frontend
type/build and all 152 tests were repeated afterward.

The final PAIR review cases check that proposal version changes close
confirmation, the first saved decision survives a later opposite choice, and
approval without a confirmed execution result has no execution retry control.
