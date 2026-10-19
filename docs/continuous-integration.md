# Continuous integration (RF-708)

[The GitHub Actions workflow](../.github/workflows/ci.yml) runs on pushes, pull
requests, and manual dispatch. It uses two independent Ubuntu 24.04 jobs:

| Job | Checks |
| --- | --- |
| Quality and fixture evaluations | Locked installs, `pnpm check`, no skipped backend tests, and the fixture evaluation pipeline |
| Container integration | Pinned image builds, initialization failure/startup order, health, permissions, persistent data, and database recovery |

A job failure makes the workflow fail. New runs cancel older runs for the same
branch or pull request. Both jobs have twenty-minute timeouts. There are no path
filters that silently omit checks for a change.

## Quality job

Node comes from `.nvmrc`; pnpm comes from the `packageManager` field. Python
3.14.6 and uv 0.12.1 match the API container toolchain. pnpm and uv caches speed
up installs, while frozen/locked dependency checks remain mandatory. Actions
are pinned to full commit IDs with release comments; update the commit and
comment together when intentionally upgrading an action.

`pnpm check` runs Python formatting/lint, generated-client drift, Python and
TypeScript checks, the production web build, all backend tests, and frontend
interaction tests. CI adds JUnit and XML coverage reports without changing the
local check command or imposing a new coverage threshold.

A disposable pgvector/PostgreSQL 17 service provides the test/evaluation database.
Its test-only role can create databases, so startup tests run rather than skip.
The service database stays unmigrated: tests and evaluations create their own
schemas or databases and clean them up. Application migrations are verified
through the startup tests and the separate container job. An explicit JUnit
check rejects skipped backend tests, including a missing database/permission
configuration that would otherwise produce a partial green run.

The evaluation steps execute the existing public CLIs in order:

1. `evaluate_workspace.py` executes all approved fixture cases.
2. `score_workspace.py` applies the approved deterministic checks.
3. `judge_workspace.py --judge fixture` exercises judging without a provider.
4. `report_workspace.py` validates the artifact bundle and renders Markdown.

Each step's existing exit contract determines success. CI does not change case
labels, thresholds, or failure interpretation. Fixture judging retains unmeasured
semantic quality. A green workflow is evidence of passing automated checks and
fixture mechanics, not a live model-quality or provider-billing result.

## Container job

The container job invokes the same standard-library smoke driver as
`pnpm docker:smoke`. Its Docker builds install their own locked dependencies;
the host runner does not need a web dependency install. The smoke creates a
random project, volume, and local ports, then removes its own resources. See
[container startup](container-startup.md) for its exact behavior and limits.

## Credentials and reports

The workflow requests only `contents: read` and disables persisted checkout
credentials. It uses ordinary `pull_request` events, with no privileged
`pull_request_target` execution. These checkout controls use the action's
[documented inputs](https://github.com/actions/checkout#usage).

Provider keys/models are empty, application `DATABASE_URL` is empty, and model
modes are offline. Only explicit test/evaluation database URLs point to the
runner's disposable PostgreSQL service. No repository secrets, deployment
credentials, image publishing, or model-call opt-in are configured.

The quality job uploads an explicit report list even after failure: JUnit, XML
coverage, and the fixture observation/metric/judgment/Markdown bundle. Reports
are retained for seven days. Local copies live in ignored `artifacts/`; Docker
also excludes that directory. Reports contain synthetic test/evaluation data;
CI never reads a project `.env` or uploads a database dump.

## Reproduce locally

Use the pinned Node version and locked dependencies, then provide a disposable
PostgreSQL URL with pgvector and a role that can create schemas/databases:

```bash
nvm use
pnpm install --frozen-lockfile
uv sync --directory apps/api --locked
export TEST_DATABASE_URL=postgresql://localhost/resolveflow_ci
export EVALUATION_DATABASE_URL="$TEST_DATABASE_URL"
pnpm check
```

To replay the fixture pipeline, choose a new output directory or new filenames.
The existing CLIs never overwrite reports:

```bash
mkdir -p artifacts/evaluation
uv run --directory apps/api python scripts/evaluate_workspace.py --output ../../artifacts/evaluation/observations.json
uv run --directory apps/api python scripts/score_workspace.py --input ../../artifacts/evaluation/observations.json --output ../../artifacts/evaluation/metrics.json
uv run --directory apps/api python scripts/judge_workspace.py --judge fixture --input ../../artifacts/evaluation/observations.json --output ../../artifacts/evaluation/judgments.json
uv run --directory apps/api python scripts/report_workspace.py --observations ../../artifacts/evaluation/observations.json --metrics ../../artifacts/evaluation/metrics.json --judgments ../../artifacts/evaluation/judgments.json --output ../../artifacts/evaluation/report.md
pnpm docker:smoke
```

## Activation and verification

The workflow starts running on GitHub once the changes are committed and pushed
to the repository. Required merge checks are a separate repository setting; the
workflow alone does not enable branch protection. Its displayed job names are
**Quality and fixture evaluations** and **Container integration**.

RF-708 implementation was verified locally on 2026-10-18. Actionlint 1.7.12
accepted the workflow, and each configured action input was checked against its
exact pinned official action definition. The quality job's shell steps were read
from the workflow and replayed with a disposable PostgreSQL service: locked
installs, all quality/build/client checks, 871 backend tests with zero skips,
206 frontend tests, and the complete fixture pipeline passed. All 20 scenarios
completed without executor errors; 123 deterministic checks passed, six semantic
checks stayed unmeasured, and fixture judging had no failures/errors while
retaining 15 unmeasured rubric checks. The Markdown artifact bundle was produced.
The container job command also passed against isolated Docker resources.

RF-708 is DONE for the implemented and locally verified workflow. The first
GitHub-hosted run remains unverified until a commit is pushed. No commit, push,
repository setting change, live model call, or deployment was performed. The
project database is unchanged.
