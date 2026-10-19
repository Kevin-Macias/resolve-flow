# Container startup (RF-707)

Compose starts a local stack in this order:

```mermaid
flowchart LR
    DB[PostgreSQL healthy] --> Init[Initialize schemas]
    Init --> API[API schema readiness]
    API --> Web[Web health]
```

## Start and stop

From the repository root:

```bash
pnpm docker:up
```

The `initialize` service uses the API image to run `python -m api.bootstrap`.
It upgrades Alembic application migrations and initializes the LangGraph
checkpoint schema. Its PostgreSQL advisory lock serializes competing
initializers for the same database. Both steps can run again against an existing
database; they preserve saved data. Initialization has bounded lock, connection,
and child-process waits and exits nonzero on failure. API workers never migrate.

The API starts only after initialization exits successfully. The web service
starts only after the API health check passes. This uses Compose's
[dependency conditions](https://docs.docker.com/compose/how-tos/startup-order/).
A failed initializer leaves application containers stopped; inspect its fixed
JSON outcome with `docker compose logs initialize`, resolve the migration or
database issue, then rerun startup. Use trusted manual migration commands for
more detailed diagnostics; raw SQL/driver exceptions are suppressed in startup
logs because they can expose sensitive values.

For an image/schema upgrade, stop application traffic before applying migrations:

```bash
docker compose stop web api
pnpm docker:up
```

This local sequence does not provide zero-downtime schema upgrades or automatic
rollback. Follow backup and compatibility procedures before changing a database
engine version. An unfamiliar newer migration revision causes initialization
or readiness to fail rather than being silently accepted by an older API.

Stop with `pnpm docker:down`. The default volume remains
`resolve-flow-postgres-data`. `POSTGRES_VOLUME_NAME` can select a separate volume;
keep its existing value when restarting a stack whose data you want to retain.
`docker compose down --volumes` deletes that stack's configured database volume.

Ports bind to localhost. `POSTGRES_PORT`, `API_PORT`, and `WEB_PORT` still choose
the host ports. The web image embeds `VITE_API_URL` and authentication mode at
build time; rebuild it when those values change. Container-internal API/web
ports remain 8000/3000. Set `CORS_ORIGINS` to the browser's web origin.

A fresh database has no user accounts. Create an administrator interactively:

```bash
docker compose exec api python scripts/manage_auth.py create-admin --email admin@example.com
```

Then use [invitations and access management](authentication-and-access.md).
Startup does not seed credentials, demo users, knowledge embeddings, or live
model calls. Offline model modes remain the defaults.

## Images and runtime permissions

Python, Node, uv, and pgvector base images are pinned by version and manifest
digest in the Dockerfiles/Compose file. Node matches `.nvmrc`; uv/pnpm install
from the committed lockfiles. Updating a base image is an explicit source change
that should rerun the smoke test. Only Linux amd64 was exercised here.

The API uses a build stage for uv/dependencies and installs the project without
an editable source link, following the [uv container guidance](https://docs.astral.sh/uv/guides/integration/docker/).
Its runtime includes migrations, checkpoint dependencies, the trusted admin CLI,
and the curated knowledge files. The web build includes `packages/api-client`
so the workspace import resolves inside Docker, then copies only Nitro output
to its runtime. Neither runtime needs a package install or source mount at boot.

API and web run as non-root users. Compose gives both applications and the
initializer a read-only root filesystem, bounded temporary storage, dropped
Linux capabilities, and no-new-privileges. Docker's init process forwards
signals/reaps children; applications have a thirty-second shutdown grace period.
Interrupted workflow operations still use their existing explicit recovery
contracts. PostgreSQL retains its image's own startup/user handling and writable
data volume.

The Docker build context excludes environment files, local credentials, caches,
and installed dependencies. Public `.env.example` files remain available.

## Health and readiness

- API `/health` reports process liveness without requiring PostgreSQL.
- API `/ready` checks database connectivity, exact application migration heads,
  and the checkpoint migration version expected by the installed library.
- The API image's probe uses `/ready`; the web image probes its own HTTP server.

Readiness performs reads only and never initializes or repairs schemas. Missing,
older, or unknown schema versions return a sanitized 503. Connection/query and
probe waits are bounded. During a database outage, `/health` can remain 200 while
`/ready` returns 503. API connection pools check existing connections before
reuse after a database restart.

Compose dependencies control initial startup. They do not continuously stop the
web service when the API later becomes unhealthy, or restart a container merely
because its health status changes. Application errors remain visible to clients;
restart policies handle exited processes. Hosting needs its own routing and
availability policy for deployment.

For a platform without Compose, build the API image, run
`python -m api.bootstrap` once as a release/pre-deploy command with the intended
`DATABASE_URL`, then start API instances. Their image must retain the shipped
migration directory and `RESOLVEFLOW_API_ROOT=/app`. Use the same build for the
release command and API. Deployments, database privilege separation, public
networking/TLS, and production credentials remain RF-710 decisions.

Host development still uses the documented explicit Alembic and checkpoint
setup commands; `/ready` requires both before it reports success.

## Verification

`pnpm docker:smoke` builds images and verifies failed initialization blocks the
applications, fresh startup/probes, non-root/read-only runtime settings,
recreation with a persistent account, and database outage/recovery with a database-backed authentication request. It uses a
random Compose project, its own volume, controlled offline environment values,
and unused local ports. It removes its containers, volume, and image tags after
running. It does not use the project's default database volume.

Startup integration tests use separate disposable databases and cover concurrent
initializers, existing data, schema mismatch/missing checkpoints, failed
migrations, and credential-safe failure logs. Their test role needs CREATEDB;
without it these cases report a clear skip.

Verification on 2026-10-18: `pnpm check` passed formatting/lint, generated-client
drift, Python/TypeScript checks, production build, all 871 backend tests, and all
206 frontend tests with no skips. Seven startup integration cases passed as
part of that run. The real Docker smoke passed failed-initialization gating,
fresh startup, non-root/read-only settings, data persistence across recreation,
and database outage/recovery. Authentication returned its expected response on
the first request after the database restart, exercising pool reconnection.
A final focused type check also passed after that smoke assertion was added.

RF-707 is DONE under DELEGATE ownership. Verification used only disposable
projects, volumes, and databases. The existing project database is unchanged;
no live model calls, account provisioning, or deployment were performed.
