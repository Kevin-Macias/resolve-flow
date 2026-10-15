# Frontend behavior coverage (RF-510)

Status: DONE. On 2026-10-13, the audit and 15 added regression cases passed with
all 184 frontend tests, TypeScript checks, and the production build. Ownership
is DELEGATE. Application behavior and API contracts are unchanged.

## Coverage map

Counts describe the verification run above. Tests use Vitest, Testing Library,
jsdom, the real router/session/query components, and controlled HTTP or stream
responses. Fixtures are validated by the same runtime schemas used in the UI.

| Area and suite under `apps/web/src/features/` | Cases | Behavior covered |
| --- | --- | --- |
| `reports/screens.test.tsx` | 13 | CRUD, loading/empty states, validation, safe errors, archive confirmation, uncertain writes, and session isolation |
| `workflow-stream/stream.test.ts` | 50 | SSE byte framing, Unicode, closed snapshots, ordering/duplicates, cursors, bounded reconnects/timeouts, access loss, cancellation, and late bytes |
| `customer-intake/intake.test.tsx` | 22 | Explicit start/recovery, ordered clarification answers and bounds, incomplete continuation, draft retention, stale/uncertain submissions, stream/full-read reconciliation, invalid responses, and session isolation |
| `execution-timeline/timeline.test.tsx` | 22 | Saved order/timestamps, distinct loading/empty/error states, stale refresh, response validation, access loss, report/session isolation, and separate customer identity |
| `evidence/evidence.test.tsx` | 17 | Provenance and source text, saved/pending/failed/empty/historical analysis, operation identities, uncertain submissions, stale/invalid reads, access loss, and late results |
| `approval/action.test.tsx` | 32 | Complete proposal, exact decision binding, focus/cancellation, duplicate/stale/concurrent outcomes, uncertainty, disconnects, preparation replay, unavailable execution outcomes, and isolation |
| `metrics/metrics.test.tsx` | 17 | Latest-extraction scope, zero versus missing usage, unavailable accounting, empty/pending states, refresh, stale/offline recovery, invalid data, and isolation |
| `support-workspace/workspace.test.tsx` | 11 | All real support panels together: independent loading/failure, shared access loss, late decisions/analysis, and cancellation of pending reads |

The individual support suites deliberately isolate neighboring sections. The
new workspace suite mounts the actual timeline, evidence, action, and metrics
panels together, including their hooks, validators, and generated API client.
It replaces HTTP responses without replacing those components.

## Gaps closed by this ticket

| Added cases | Regression they detect |
| --- | --- |
| Independent section loading; evidence failure and targeted refresh | A slow read blocks other sections, a failure appears as empty evidence, or refresh starts work or refetches unrelated sections |
| Access revocation detected by each of four support sections | One section hides itself while leaving another section's protected content or approval confirmation visible |
| Pending decision followed by revocation in timeline, evidence, or metrics | A late accepted decision restores protected content after shared access loss or causes another write |
| Pending analysis followed by action access loss | Late evidence restores protected content after another section has removed access |
| Session exit while all four support reads are pending | Requests stay active or late responses repopulate a session that has ended |
| Stream completion before the full clarification response arrives | Clarification controls appear before the full saved pause is available |
| Temporary clarification read failure and recovery | Unsent answers disappear or stale controls allow another submission before reconciliation |
| Previously visible intake returns 404 | A missing or inaccessible saved run is mistaken for a fresh report on which intake can be started again |
| Invalid streamed state | The UI accepts replies despite a stream protocol failure |

These cases exercise existing reviewed behavior. They introduce no new
authorization, approval, recovery, or evaluation policy.

## Running and interpreting checks

Use the Node version from `.nvmrc`:

```bash
nvm use
pnpm test:web
pnpm typecheck:web
```

`pnpm test:web` runs all eight suites. `pnpm typecheck:web` also builds the
production application. Both passed on 2026-10-13 with no skipped tests.
No application code, backend code, or dependencies changed for RF-510.

This is a behavior audit, not a claim of complete line coverage or production
authorization verification. Controlled HTTP tests cannot establish database
transactions, durable checkpoints, server access enforcement, or browser layout.
Those have separate backend and browser verification records in the feature
documents, including [support approval](support-approval-controls.md) and
[execution metrics](execution-metrics-ui.md).

The [hands-on platform checkpoint](roadmap.md#platform-review-checkpoints) remains
pending. Customer summary confirmation, automatic workflow diagnosis/proposal
generation, and full metrics accounting remain separate work. RF-510 does not
make those planned integrations available.
