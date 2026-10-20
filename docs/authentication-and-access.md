# Authentication and access (RF-702)

Kevin accepted final PAIR implementation review on 2026-10-18. He selected
permanent invitation onboarding and email/password repeat login.

Customer (`/reports`) and support (`/support`) entry pages share a responsive
hero layout, with separate headings and links to switch areas. The navigation
header appears after sign-in. `WorkspaceSession` manages the in-memory session
and query cache; `CustomerSignIn` and `SupportSignIn` compose the shared forms.
The support entry shares the light two-column layout. Its own introduction
component uses a console label, sans-serif heading, and icon rows for reports,
evidence, and proposal review. The form has a green top border and an **Internal
access** label. A quiet customer-reports link sits below it.
On narrow screens, compact headings and spacing bring sign-in and invitation
actions forward. Introductory descriptions are hidden, and the support capability
list follows the form. Session-memory guidance sits below the actions. Fields
and buttons remain full width; longer forms scroll.

Both entry pages accept email/password sign-in and invitation setup for either
role. The validated session response determines the workspace: customers open
`/reports`, support users open `/support`. Matching workspace links, including
report URLs, stay in place. The session survives the redirect, and the other
workspace does not render with that token. Signed-in users stay within their
account's workspace; end the session to use another account. API access checks
remain authoritative. Legacy demo tokens still require separate workspace sessions.

Full-width cards stack beneath the sign-in form for invitation setup and switching
workspaces. Each has a distinct color, icon, and description; the invitation card
switches back to sign-in during setup. Invitation requests use an underlined link
inside the form card.
Set `VITE_INVITATION_EMAIL` in `apps/web/.env` (or the web service's build
variables) to show **Request an invitation**. It opens the visitor's email app
with a subject filled in. The address is public; administrators still review
requests and issue invitations manually. Restart development or rebuild the web
image after changing this value.

## Account lifecycle

A trusted local operator creates the first access administrator. That admin
creates an invitation with a fixed role and account scope. The recipient
redeems it with their chosen email, name, and password, creating a permanent user
and an initial session. Later visits use email and password.

An invitation expires after 24 hours and can be redeemed once. Redemption locks
the invitation and commits user creation, credentials, grants, consumption, and
the initial session together. Concurrent redemption creates one account. The
issuer must still be an enabled administrator. Invitations cannot reset an
existing user's password or upgrade their permissions. A registered email is
rejected without consuming the invitation, so the recipient can choose another.
Whoever redeems the token first chooses the email; mailbox ownership is not verified.
Revoke an older invitation when replacing it.

Passwords accept 15-128 characters and use pwdlib's recommended Argon2id hash.
Emails are validated and normalized with case folding. Login returns the same
401 response for an unknown email, wrong password, or disabled account. A
persisted per-email window allows ten login attempts per ten minutes, including
successful attempts; further attempts return 429 with `Retry-After: 600`.

Sessions are opaque bearer credentials with an eight-hour expiry. Only hashes
of session and invitation tokens are stored. Password hashes are separate from
user profiles. Secret-bearing responses use `Cache-Control: no-store`.
The browser keeps its session token in memory; reload requires login again.
Passwords and invitation tokens are never written to browser storage.

Logout revokes the presented session. Disabling a user revokes all their sessions
and prevents login. A local password reset also revokes all sessions and keeps
any disabled status. Current identity checks reject expired/revoked sessions,
disabled credentials, and changes to the saved role, tenant, or admin capability.
Support grants are read from current database rows at access checks.

These choices follow the [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
and [session lifecycle guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

## Set up and invite someone

Use `AUTH_MODE=password` in the API environment and `VITE_AUTH_MODE=password`
in the web environment. These are the defaults; Compose derives both from
`AUTH_MODE`. Restart the API and rebuild the web app after changing modes.
Existing demo users do not gain password credentials automatically.

From the repository root, with the root `.env` configured for the intended database:

```bash
uv run --directory apps/api --env-file ../../.env alembic upgrade head
uv run --directory apps/api --env-file ../../.env python scripts/manage_auth.py create-admin --email admin@example.com
```

The CLI prompts twice for the password without echoing it. Do not put passwords
in command arguments. This creates a support user with administrator capability
and zero report-account grants. It requires trusted database access; there is
no public admin signup endpoint.

Open the API's `/docs`, call `POST /auth/login`, and paste the returned
`access_token` into **Authorize**. Call `POST /admin/invitations` with, for example:

```json
{
  "user_type": "customer",
  "customer_account_id": "<existing customer account UUID>",
  "support_account_ids": []
}
```

For support, use `user_type: "support"`, a null `customer_account_id`, and the
explicit account UUIDs in `support_account_ids`. Accounts must already exist.
Record the invitation ID for revocation and deliver the returned token privately.
The token is returned once; the service does not send email or verify mailbox
ownership. The recipient opens `/reports` for customer access or `/support`
for support access, selects **Have an invitation?**, and enters their email, name,
and password.
Invited users cannot choose their role, tenant, grants, or admin capability.

To recover a forgotten password, a trusted local operator runs:

```bash
uv run --directory apps/api --env-file ../../.env python scripts/manage_auth.py reset-password --email customer@example.com
```

Admin operations use the API; there is no management screen or user/account
listing endpoint. Use known user and account IDs when managing access.

Migration `0010` removes invitation email bindings. Existing unused tokens also
allow a chosen email. Deploy the API and web changes together. Rolling back
`0010` revokes invitations because their original email bindings cannot be restored.

## Authentication and administration API

| Endpoint | Access and effect |
| --- | --- |
| `POST /auth/login` | Public; email/password creates a session |
| `POST /auth/invitations/redeem` | Public; one valid invitation creates an account and session |
| `POST /auth/logout` | Bearer required; revokes that token, including idempotent logout of an expired/revoked token |
| `POST /admin/invitations` | Active support administrator; creates an invitation |
| `DELETE /admin/invitations/{id}` | Active support administrator; revokes an invitation |
| `DELETE /admin/users/{id}/access` | Active support administrator; disables a non-admin user and revokes sessions |
| `PUT /admin/users/{id}/support-accounts` | Active support administrator; replaces a support user's grants with `{"account_ids": [...]}` |

Administrator is a capability of a support user, not a third role. It grants
access-management operations, not report access. Admin accounts are managed
locally and cannot be disabled through the public admin API. Re-enabling disabled
users and changing roles or customer membership have no management endpoint.

## Application access policy

Authentication establishes a current database user; authorization scopes each
operation. Report UUIDs, browser routes, source text, and saved approvals do not
grant access. The customer account is the tenant boundary; teammates in the same
account share report access. Submitter identity is attribution.

| Operation | Customer | Support |
| --- | --- | --- |
| Health, readiness, API documentation/schema | Public | Public |
| Report create/list/read/update/archive | Own account; archived reports hidden | Denied |
| Intake start/read/clarification/recovery and SSE | Own account, valid report/run binding | Denied |
| Report-state, timeline, metrics, evidence, and action reads | Denied | Explicitly granted accounts; archived reports readable |
| Preliminary evidence analysis | Denied | Granted account and eligible active report |
| Prepare/revise, approve/reject a proposal | Denied | Granted account; existing eligibility, freshness, and exact proposal guards |
| Recover simulated execution | Denied | Granted account; exact saved approval, durable intent, unchanged observations |

Support evidence includes public/internal sources and private sources for the
report's account. Grants to multiple accounts do not combine their private
sources in one analysis. Existing [support approval controls](support-approval-controls.md)
and [execution recovery](tool-idempotency.md) retain their additional guards.

401 means absent or invalid identity, 403 means wrong role/capability, and 404
hides missing, foreign-account, or ungranted records. Customer archive reads
also return 404. Stale authorized mutations return 409. Invalid/expired/used
invitations return a generic 400; redemption with a registered email returns 409.
Malformed identity configuration fails closed with 503.

Fresh support reads, stream sends, and execution checks recheck current access.
Revocation takes effect at these checks; it does not undo a completed response
or effect. If browser logout cannot reach the server, the UI clears local access
and reports that server revocation is unconfirmed.

## Legacy demo mode and limits

`AUTH_MODE=demo` and `VITE_AUTH_MODE=demo` explicitly retain existing token-map
fixtures. `DEMO_TOKEN_USER_IDS` and `DEMO_SUPPORT_ACCOUNT_IDS` are strictly
validated. Static demo credentials have no session expiry or server logout.
Password mode never falls back to those maps. Editing environment files requires
restarting all workers; database grants apply on subsequent access checks.

This implementation requires HTTPS and appropriate deployment controls when
exposed. It has no MFA, SSO, automated invitation delivery, self-service password
recovery, or automatic expired authentication-record cleanup. Login retains its
email limit; [RF-706](request-limits.md) adds shared address limits for login and
invitation redemption, plus user/account/model-operation limits. Concurrent work,
storage quotas, and provider spend caps still need separate controls. Review
deployment and operational controls before using real customer data.

## Verification

Recipient-chosen email follow-up, 2026-10-20: `pnpm check` passed with all 874
backend and 219 frontend tests, no skips, on a disposable PostgreSQL database.
Coverage includes chosen-email normalization, repeat login, duplicate-email
rejection without token consumption, required/invalid emails, and the existing
single-use and access checks. Migration `0010` upgrade, legacy-token preservation,
rollback revocation, re-upgrade, and ORM drift passed separately. The local app
was upgraded to `0010`; readiness and the running API contract passed. The earlier
manual-test token remained usable. Hands-on browser review remains Kevin's check.

[`test_accounts.py`](../apps/api/tests/identity/test_accounts.py) exercises actual
HTTP handlers and isolated PostgreSQL schemas: repeat login, tenant scoping,
hashed credentials, concurrent/expired/revoked invitations, grants, disable,
expiry, password reset, mode isolation, throttling, and permission-field injection.
[`account.test.tsx`](../apps/web/src/features/session/account.test.tsx) covers the
browser forms, safe failures, wrong-role sessions, late responses, and logout.
Existing workflow/access suites continue using explicit demo fixtures. These
checks do not replace hands-on browser verification.

Verification on 2026-10-15: `pnpm check` passed formatting/lint,
generated-client drift, Python/TypeScript checks, production build, all 794
backend tests, and all 192 frontend tests with no skips on disposable PostgreSQL.
The 13 account lifecycle cases and eight new browser interaction cases passed.
Migration `0007` upgrade/rollback and ORM drift passed in a separate disposable
database; CLI help and documentation links/whitespace passed. The first full run
hit the previously recorded checkpoint restart flake; it passed in isolation
and in the full rerun without changes to that test. The project database is
unchanged. No live providers or hands-on browser verification were used.
