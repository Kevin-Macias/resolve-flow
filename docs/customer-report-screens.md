# Customer report screens (RF-502)

Status: implemented; Kevin's final review pending.

Kevin will review the UI at the [platform checkpoint](roadmap.md#platform-review-checkpoints).
He can use the CRUD walkthrough below earlier; hands-on review remains pending.

## Available behavior

The frontend now opens My reports at `/reports`. It uses the generated API
client and TanStack Query for list/detail reads and create/update/archive writes.

- `/reports`: description previews, report status, affected service, and updated
  time, with loading, refresh, unavailable, and empty states.
- `/reports/new`: submit a nonblank description of at most 5,000 characters and
  an optional existing service code. Failed submissions preserve entered values.
- `/reports/$reportId`: original description, service, status, and timestamps;
  edit or clear the service and explicitly confirm archival.

List links use a description preview because the API has no title. Description
and status are read-only after creation. Service editing accepts a known code
as text, or `null` to clear it; a service-list endpoint is unavailable.

Archiving succeeds only on HTTP 204, invalidates the list, removes the detail
cache, and returns to My reports. A 404 means unavailable, never proof that the
report was archived. Restore and support archival-history views are not present.

## Demo identity and local setup

The browser keeps the demo token in memory and sends a bearer header.
`DEMO_TOKEN_USER_IDS` resolves it to a database user and account; the UI cannot
grant roles or select arbitrary accounts. Session exit clears queries/forms and
ignores late results, including navigation. Accepted server writes remain saved.

Use a configured, migrated local PostgreSQL database. If a suitable customer
already exists, use its user UUID. For a fresh local database, the following SQL
creates a demo account and customer; run it explicitly through your database
client and copy the returned user ID:

```sql
WITH account AS (
  INSERT INTO customer_accounts (name)
  VALUES ('ResolveFlow local demo')
  RETURNING id
)
INSERT INTO users (customer_account_id, user_type, name, last_name)
SELECT id, 'customer', 'Demo', 'Customer' FROM account
RETURNING id;
```

Map a chosen local token to that UUID in the API environment, for example:

```bash
export DEMO_TOKEN_USER_IDS='{"local-customer":"<returned-user-uuid>"}'
```

For host development, set `DATABASE_URL` to your local database and launch
`pnpm dev` from that shell. For Docker, set `DEMO_TOKEN_USER_IDS` in the root
`.env`; Compose now passes it to the API. Restart the API after changing the
mapping. Apply migrations before using report screens; host migrations can run
with `uv run --directory apps/api --env-file ../../.env alembic upgrade head`
when the root `.env` supplies the correct host database URL.

Open the web app and enter `local-customer`. A support user token is denied by
the existing customer CRUD API. You can leave the service blank. To exercise
service editing, use a code already present in the database's `services` table.
No tokens belong in `VITE_` variables or source control; `.env.example` contains
only an empty mapping. This remains simulated identity, not production login.

## Styling

The list groups reports into a single panel with status badges, service and
updated-time metadata, and an empty state with a create action. The new-report
page pairs the form with writing guidance; on smaller screens the guide follows
the form. The character limit and reminder that descriptions stay as submitted
appear beside the form controls. Both pages share the login palette and brand.

The report screens use Tailwind through its Vite plugin. `styles.css` imports
Tailwind and defines theme tokens, base typography/focus rules, and shared
classes for buttons, cards, fields, notices, and labels. See the
[frontend styling agreement](working-agreement.md#frontend-styling) for usage.
The desktop/mobile
layout and accessible focus states remain part of platform verification. The
Tailwind follow-up passed the production build, strict TypeScript checks, all 11
existing frontend interaction tests, and the desktop/mobile Chromium walkthrough
with mocked HTTP responses. No backend behavior changed.

The setup follows [Tailwind’s Vite installation guide](https://tailwindcss.com/docs/installation/using-vite).

## Queries, writes, and errors

Each rendered application owns a QueryClient with token-scoped list/detail keys.
Session exit cancels reads and clears it; queries forward cancellation signals.
Create/update success replaces detail data and invalidates the list. Forms keep
local state separate from server data. `features/reports/validation.ts` defines
shared Zod schemas for report creation, service updates, and demo token entry;
see the [validation agreement](working-agreement.md#frontend-validation).
`response-validation.ts` checks report/list response shapes, IDs, statuses, and
timestamps before query caching. Invalid responses show a fixed safe message.

Writes never retry automatically. Pending writes disable their form controls.
A failed create explains that the report may already have been saved and asks
the user to check the list before repeating it. After a failed archive, the user
must successfully refresh the report before another attempt; cancellation of
the confirmation does not bypass this rule. Reads can be refreshed explicitly.

HTTP 401/403, validation failures, missing reports, server failures, and network
failures have distinct safe messages. Raw backend exceptions or response content
are not displayed. Query failures hide stale report content until a successful
read. An unknown service code keeps the edit form available for correction.

## Verification and review

Verification on 2026-10-09: root `pnpm check` passed format/lint, generated-client
checks, frontend/API type checks, 410 backend tests, and 11 frontend tests. Forty
existing database tests were skipped without `TEST_DATABASE_URL`. Compose demo
identity interpolation and local documentation links were also checked.

`pnpm test:web` runs the Vitest/Testing Library interaction suite and is included
in root `pnpm check`. Tests exercise the actual generated client with mocked
HTTP responses, routing, queries, and forms: create/read/edit/clear/archive,
confirmation cancellation, loading/empty/refresh states, validation and network
errors, unavailable/unauthorized reads, no automatic write retries, uncertain
archive recovery, and session isolation including late writes.

Chromium passed production routing/hydration, create/read/edit/archive, session
exit, and desktop/mobile layouts without overflow or page errors. It used HTTP
mocks and made no database writes. A real database-backed browser walkthrough
remains pending; backend integration tests provide separate coverage.

Kevin's walkthrough: create a report; open it from the list; edit and clear its
service; cancel an archive once, then confirm it; verify the list refreshes. Try
an invalid service code and another demo customer identity. Review that original
text and status remain read-only and that a missing detail does not claim
archival. Report details now include [customer clarification controls](customer-clarification-ui.md)
and customer-safe streaming through RF-505. Internal evidence, approval, and
the remaining workflow integration remain planned under RF-501.

Reference: [TanStack Query's mutation guide](https://tanstack.com/query/latest/docs/framework/react/guides/mutations)
explains the query-cache updates and invalidation pattern used here.
