# Issue-report visibility within a customer account

Intended visibility: INTERNAL. Source version: 1. Authored: 2026-10-06.

## Applicability

Use when a customer reports a missing report and the account context may differ
from the context used at creation. Current API behavior.

## Checks

Establish the current account through trusted application identity. If an
existing authorized creation response is available, compare its owning account
with the account for which the investigation is authorized. Never request tokens
or accept a model-supplied account ID as authorization.

## Interpretation

Ownership is assigned from trusted identity during creation. Listing includes
only non-archived reports in the current account. Users in the same account
share this scope; a different user does not necessarily mean a different account.
An other-account report produces the same customer read HTTP 404 as an absent
or archived report.

## Next steps and limits

Explain account-scoped visibility. Do not expose another account's report or
probe its existence. If a context mismatch is suspected but cannot be verified
within permitted evidence, retain it as a hypothesis. The current frontend has
no account-switching control; this guide does not prescribe one or grant support
access through the customer endpoints.
