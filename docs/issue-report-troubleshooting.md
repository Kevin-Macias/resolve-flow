# Issue-report submission and visibility

RF-401 uses the complaint: “I submitted an issue report, but I can't find it
in my list.” The missing report is investigated through a new intake report.
Creating a support ticket records the investigation; it does not restore the
missing report.

## Existing API behavior

- Successful creation commits a report and returns HTTP 201 with its ID,
  owning customer account, and `submitted` status.
- Descriptions are trimmed and must contain 1–5,000 characters. Unknown body
  fields and unknown affected service codes are rejected with HTTP 422.
- Ownership comes from trusted simulated identity, not the creation body.
- Listing returns non-archived reports belonging to the current account.
  Different users in the same account share this account scope.
- Reading by ID returns HTTP 404 for missing, archived, or other-account
  reports. That response alone cannot distinguish those explanations.
- Archiving returns HTTP 204 and sets status to `deleted`. The row remains
  stored but disappears from customer list and read responses.
- Customer updates can change or clear the affected service, but cannot change
  the description or status. There is no customer restore operation.

Sources: [routes](../apps/api/src/api/issue_reports/router.py),
[schemas](../apps/api/src/api/issue_reports/schemas.py),
[service validation](../apps/api/src/api/issue_reports/service.py), and
[integration tests](../apps/api/tests/issue_reports/test_issue_reports_api.py).

## Troubleshooting distinctions

| Possible explanation | Useful evidence | Limitation |
| --- | --- | --- |
| Submission rejected | Validation response for the same attempt | Does not explain a different successful submission |
| Report archived | Authorized current-state lookup for the same ID (planned RF-512) | Currently unavailable to support; a 404 alone cannot prove archival |
| Different account context | Trusted current account and an authorized creation record | Do not probe or disclose another account's records |
| Unknown submission outcome | No saved response or report ID | Do not assume success or failure |

A runbook explains general behavior. It does not prove what happened to a
particular report. Checks requiring unavailable operational evidence must be
identified as unavailable rather than invented.

## Planned frontend connection

Phase 5 will expose report creation, listing, viewing, and archiving. The
customer assistant will clarify the complaint; the support workspace will show
reference passages, a diagnosis with uncertainty, and a proposed simulated
support ticket when investigation is needed.

The current frontend is a health-check placeholder. No restore control, account
switcher, archive audit history, or support lookup endpoint is added here.

## Planned support lookup (RF-512)

Add a read-only support lookup that can return current report state, including
`deleted`, only within application-authorized account scope. Verify permitted
reads, denied access, missing reports, archived reports, and unchanged customer
read behavior. Kevin reviews the authorization contract before implementation.

This capability must precede a frontend demonstration of verified archival. It
does not add restoration or archive history; who archived a report and when
remain separate future work.
