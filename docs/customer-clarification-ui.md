# Customer clarification UI (RF-505)

The customer report detail at `/reports/{report_id}` now includes intake controls.
Use a configured customer demo token and the database setup in
[customer intake runs](customer-intake-runs.md). The default provider is labeled
**Offline simulation** beside the workflow state.

## Customer flow

1. Open an authorized report. Reading the page does not start a workflow.
2. Choose **Start intake**. The saved response supplies the current questions.
3. Answer every question, then choose **Submit answers**. Answers are trimmed,
   retain question order, and accept 1–2,000 Unicode characters each. Zod checks
   form values and API responses before use.
4. Read accepted questions and answers under **Previous answers**. A later pause
   replaces the form; the backend permits at most two answered rounds.
5. Alternatively, choose **Continue with incomplete context** and confirm. This
   sends no draft answers and displays the saved incomplete-context label.

The current backend stops at `needs_confirmation`. The page explains that summary
confirmation is still pending implementation; reaching that state does not
create a support ticket. A pause with no further questions offers only explicit
incomplete continuation.

## Saved state, streams, and recovery

Full GET responses contain questions and accepted answers. SSE supplies a safe
progress snapshot with its own revision and connection state. A newer snapshot
blocks obsolete controls until a full saved view arrives. Stream completion
refreshes the full view. Neither GET nor SSE advances the workflow.

Every answer command carries a fresh operation UUID, the displayed revision,
and the saved pause UUID. Pending requests disable controls, with an additional
synchronous guard against double submission. Successful commands replace the
cached full view returned by the API; no optimistic answer is presented as saved.

Failed or uncertain writes require **Refresh saved intake** before another
command. The client never automatically retries a mutation. A stale revision
returns a safe error; refreshing shows the answer accepted by another tab.
Temporary read failures preserve the current draft and show a stale notice while
commands are disabled. A new pause discards the old form. Drafts are held in
memory and do not survive page reload; accepted answers do.

**Recover saved operation** appears only for a durable pending operation. It
uses the displayed revision and explicitly asks the backend to recover the
accepted operation. Pending state alone cannot establish whether a worker is
still running; the backend lock and operation records decide the outcome.

Access loss removes the report, questions, and accepted answers. Requests from
an ended demo session cannot restore protected content. Customer intake uses
the route's customer session and never calls internal support endpoints.

## Code map

Under `apps/web/src/features/customer-intake/`:

- `schemas.ts` validates forms and the closed customer response contract.
- `api.ts` wraps generated client operations and maps safe error messages.
- `use-customer-intake.ts` manages saved queries, explicit mutations, refresh,
  and access loss. Its refs guard against late results and duplicate submissions.
- `use-intake-stream.ts` owns stream subscriptions, cleanup, connection status,
  and selection of the newest snapshot for the current run.
- `components/` renders the panel, current clarification, and accepted turns.
- `intake.test.tsx` exercises the report screen, API wrapper, and SSE client.

## Verification

On 2026-10-12, `pnpm check` passed **518 backend tests and 103 frontend tests**
with no skips, plus lint, formatting, type checks, generated-client verification,
and the production web build. The 18 new frontend cases cover two rounds,
ordered answers, Unicode limits, incomplete continuation, duplicate submissions,
uncertain writes, stale revisions, recovery, stream refresh, response validation,
and access/session loss.

A Chromium walkthrough used the production build, real HTTP/SSE, and a disposable
PostgreSQL database. It verified explicit start, persisted answers after reload,
read-only refreshes, incomplete continuation, draft preservation during an API
outage, a stale answer after another actor consumed the pause, and revoked-token
access loss. Desktop and mobile layouts had no horizontal overflow or runtime
errors. Recovery used a deliberately interrupted accepted start before graph
dispatch, then the normal API and UI recovery path. No application test endpoint
or intercepted browser response was used.

The live walkthrough used the default one-round offline script; two-round behavior
is covered by contract fixtures in frontend tests and the backend suite. No live
model call ran. Kevin's broader platform walkthrough remains pending as recorded
in the [roadmap](roadmap.md).
