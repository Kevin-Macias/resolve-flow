# Railway demonstration (RF-710)

Kevin selected Railway Hobby on 2026-10-18. Services were provisioned and public
HTTPS checks passed on 2026-10-19. Administrator setup, authenticated browser
verification, and final PAIR review remain pending.

## Hosted environment

- Project: `airy-celebration`, environment: `production`, region: `iad`.
- Web: <https://resolve-flowweb-production.up.railway.app>, retaining the existing
  Railway service name `@resolve-flow/web`.
- API: <https://api-production-98d1.up.railway.app>.
- Database: private `db` service with `db-volume` mounted at the path below.
- Source revision for the initial deployment: `ff9d31e` on `main`.

The CLI is authenticated and linked. The database password was generated and
sent directly to Railway; it is not stored in this repository. API/web use the
existing Dockerfiles, explicit ports 8000/3000, readiness checks, password
authentication, and offline model modes. The existing web service's start-command
override is `node .output/server/index.mjs` to match the Docker runtime.

The compute usage limit was unset when inspected; no workspace billing limits
were changed. The Railway Agent's separate default limit does not cap service
hosting costs.

Use three services named `db`, `api`, and `web` in one project/environment.
Keep one replica per service and place them in the same region. Start with
password authentication, fictional demonstration data, offline model modes,
and the existing simulated ticket tool. Live provider configuration is a later
explicit step.

## Service settings

| Setting | db | api | web |
| --- | --- | --- | --- |
| Source | Pinned image below | This repository | This repository |
| Repository root | — | `/` | `/` |
| Dockerfile | — | `apps/api/Dockerfile` | `apps/web/Dockerfile` |
| Start command | Image default | Image default | Image default |
| Pre-deploy command | — | `python -m api.bootstrap` | — |
| Pre-deploy timeout | — | 300 seconds | — |
| Deployment health path | — | `/ready` | `/reports` |
| Health timeout | — | 300 seconds | 300 seconds |
| Persistent volume mount | `/var/lib/postgresql/data` | None | None |
| Public HTTPS domain | None | Generate | Generate |

Database image, matching the locally tested PostgreSQL 17/pgvector build:

```text
pgvector/pgvector:0.8.7-pg17-bookworm@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d
```

Use an image service for the database. The default PostgreSQL template does
not include pgvector; the pinned image supplies it. Keep database image updates
manual and retain the volume when replacing the container. Initial credentials
initialize an empty volume; changing environment values later does not rotate
the saved database password.

Both application Dockerfiles require the whole repository as their build
context. Selecting `apps/web` or `apps/api` as the service root would omit
required files. Railway supplies `PORT`, which both app entry points honor.
The web's `/` route redirects; use `/reports` for Railway's readiness check,
which requires a successful page response.

## First deployment

1. Create an empty Railway project in the Hobby workspace. Configure a compute
   usage alert and hard limit using Kevin's chosen budget. The Hobby minimum
   includes usage credit; total resource usage can exceed it. A hard limit takes
   workloads offline when reached. Provider API bills are separate.
2. Add `db` from the pinned image and attach its volume before starting it.
   Copy [database variables](../deploy/railway/db/.env.example) into Railway's
   variable editor. Replace the password placeholder with a generated long
   alphanumeric secret; this avoids URL-encoding ambiguity. Keep the database
   private, with no public TCP proxy. Wait until it accepts connections.
3. Add `api` and `web` from the repository, with automatic deployment disabled
   during setup. Select the revision containing this work after it has been
   reviewed and pushed. Configure the service settings above and generate the
   public domains. Set [API variables](../deploy/railway/api/.env.example) and
   [web variables](../deploy/railway/web/.env.example), replacing both domain
   placeholders with their actual HTTPS origins.
4. Deploy `api`. Confirm the pre-deploy initializer succeeds and `/ready`
   returns 200. Deploy `web`, then check the login page. Configure runtime
   `API_ORIGIN` and `WEB_ORIGIN` using the cookie rollout below. Database
   credentials and model keys belong only on the API/database services, never
   in `VITE_` variables.
5. In an authenticated Railway shell for `api`, run the shipped admin command:

   ```bash
   python scripts/manage_auth.py create-admin --email YOUR_ADMIN_EMAIL
   ```

   Enter the password at the hidden prompts. Follow
   [invitation and grant setup](authentication-and-access.md#set-up-and-invite-someone).
   Customer accounts must exist before issuing invitations. A fresh database
   has no tenants or demonstration reports; choosing and provisioning fictional
   demo records remains part of the deployment walkthrough.

   With the CLI linked to the hosted project, open the API shell using:

   ```bash
   railway ssh --service api --environment production
   ```

   Run the admin command inside that shell. Choose the password there rather
   than sharing it in chat or putting it in command arguments.

The variable examples contain Railway references, not shell substitutions.
Paste them into Railway; do not source them in a terminal. Store real secrets
in Railway, keeping these checked-in examples unchanged.

## Verification before accepting RF-710

Verified on 2026-10-19 against the hosted services:

- Railway reports successful database, API, and web deployments.
- API `/health` and `/ready` return 200, including database/schema readiness.
- Anonymous `GET /issue-reports` returns 401.
- Login preflight permits the exact HTTPS web origin.
- Web `/reports` returns 200 with the password login page, and its deployed
  JavaScript contains the configured HTTPS API origin.

The initial web readiness check received HTTP 307 from `/`; changing its path
to `/reports` resolved readiness. Superseded deployments using the old check were
canceled. These HTTP and bundle checks do not replace an authenticated browser
walkthrough. No administrator, customer accounts, or invitation credentials were
created, and no live model calls were made.

Verify customer onboarding, repeat login, cross-account denial, clarification
and streaming, support grants, evidence, exact-action approval, simulated
execution, and saved history in a real browser. Recreate the API container while
a workflow is paused, then resume it using the saved state. Confirm logs contain
correlation metadata and exclude credentials/content. Observe actual resource
usage before choosing whether to enable live model calls.

Check database backup configuration and perform a restore rehearsal before
relying on saved demonstration data. Platform storage does not by itself prove
recoverability. Application/database privilege separation remains an operational
follow-up: this initial setup uses the database owner for initialization and
runtime, as the current local deployment does.

Railway deployment health checks do not continuously monitor an active service.
The API also retains the existing request-limit behavior behind a proxy:
forwarded client addresses are ignored, so visitors may share the proxy's
address allowance. See [request limits](request-limits.md). Keep this limitation
visible during hosted verification rather than trusting arbitrary forwarded
headers.

For schema-changing upgrades, stop application traffic and back up the database
before running initialization. The pre-deploy command runs while an old release
may still exist; it does not establish migration compatibility or automatic
database rollback. Follow the [container upgrade contract](container-startup.md).

## Platform references

- [Dockerfiles and build variables](https://docs.railway.com/builds/dockerfiles)
- [Monorepo build context](https://docs.railway.com/deployments/monorepo)
- [Pre-deploy commands](https://docs.railway.com/deployments/pre-deploy-command)
- [Deployment health checks](https://docs.railway.com/deployments/healthchecks)
- [Private networking](https://docs.railway.com/networking/private-networking)
- [PostgreSQL extensions](https://docs.railway.com/databases/postgresql)
- [Usage controls](https://docs.railway.com/pricing/cost-control)
- [Interactive service shells](https://docs.railway.com/cli/ssh)

Dashboard settings are used for this first deployment. Railway's former
`railway.json`/`railway.toml` format is deprecated for new services; repeatable
project automation can use its current
[Infrastructure as Code](https://docs.railway.com/infrastructure-as-code) support
after the hosted settings have been verified.

## Cookie session rollout

Kevin approved the same-origin web proxy on 2026-10-20. It uses the existing
web/API/database services and session tables; this change needs no migration.
Browser password traffic, including SSE, goes to the web service's `/api` route.
FastAPI continues to authenticate bearer requests from the proxy and CLI clients.

Set these runtime variables on the Railway web service:

- `WEB_ORIGIN=https://resolve-flowweb-production.up.railway.app`
- `API_ORIGIN=https://api-production-98d1.up.railway.app`

Use exact origins without paths. Production requests fail closed if either is
missing or invalid. The API origin is server-only configuration. Keep
`VITE_AUTH_MODE=password`; an existing `VITE_API_URL` is ignored by password
sessions and remains relevant only to explicit legacy demo-token sessions.
No custom domain or new service is required. API CORS settings may remain.

Deploy the API first so `GET /auth/session` is available, then the web build
with these runtime settings. Existing memory-only browser sessions require a
fresh login. Verify login, reload on a report deep link, customer/support role
routing, expiry/revocation, logout followed by reload, rejected cross-site
writes, and a live intake event stream. Confirm the HTTPS cookie is host-only,
HttpOnly, Secure, and SameSite=Lax and browser responses contain no bearer.
The API's existing shared peer-rate allowance now also sees traffic from the
web proxy; forwarded browser IP headers remain untrusted and ignored.

On 2026-10-21 Kevin accepted the local implementation and requested the commit
and Railway configuration. Commit `30005fa` contains the verified session change.
Both runtime origins above were saved on the existing production web service
with automatic deployment suppressed. `VITE_AUTH_MODE` remains `password`.

The API-first rollout attempt returned `Deploys have been paused temporarily`.
No new deployment was created; the API still runs its previous successful
release. Railway's [status page](https://status.railway.com/) reported an active
outage affecting builds and deployments. The current web `/reports` and API
`/health` and `/ready` endpoints each returned HTTP 200 after the attempt.

Retry the API deployment once Railway resumes builds, wait for readiness, then
deploy the web service and perform the authenticated checks above. The saved
origin variables are already configured. Hosted cookie verification and Kevin's
hands-on acceptance remain pending.
