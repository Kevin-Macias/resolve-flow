# Curated knowledge dataset (RF-401)

Status: DONE. Kevin approved the issue-report submission and visibility scope
and completed the PAIR review of the eight-document [corpus](../knowledge/README.md).

## Goal

The eight sources help investigate “I submitted an issue report, but I can't
find it in my list.” See the [feature summary](issue-report-troubleshooting.md)
for API behavior and planned UI. Guides describe the API; investigations and
superseded legacy advice are fictional fixtures.

## Draft source set

| Source | Purpose | Distinguishing information |
| --- | --- | --- |
| Submission validation runbook | Rejected submission | Validation response, description constraints, unknown service code |
| Archived report runbook | Previously created report disappears | Archive semantics and limits of a 404 |
| Account-scoped visibility runbook | Report absent in current account | Trusted identity and same-account versus other-account access |
| Superseded visibility guide | Stale advice with matching keywords | Invented legacy advice to include archived reports; explicit replacement link |
| Affected-service update guide | Plausible irrelevant text | Service updates and validation do not explain a missing report |
| Resolved missing-report investigation | Verified historical example | Fictional creation and current `deleted` state for the same ID |
| Unresolved missing-report investigation | Genuine ambiguity | No saved submission response or sufficient evidence of cause |
| Public missing-report help article | Customer-safe reference | Useful information to supply and limits of missing results |

Placement: guides under `knowledge/runbooks/`, investigations under
`knowledge/sample-incidents/`, and a corpus README indexing the sources.

## Authoring and review

Use stable filenames and headings. Guides describe applicability, checks,
interpretation, limitations, and escalation. Identify checks that need evidence
not currently exposed by the application. Do not invent operational tools.

Use the existing PUBLIC and INTERNAL vocabulary. Dates, versions, and replacement
links should be readable. RF-402 defines typed metadata; document labels alone
do not enforce authorization.

Kevin reviews the useful distinctions and important failure cases. Completion
requires similar symptoms with different causes, scoped stale advice, plausible
irrelevant material, ambiguity, consistent terminology, and valid source links.

Kevin reviewed the completed reference corpus. Retrieval, evaluation expectations,
and report recovery belong to separate tickets; RF-401 changes documentation only.

## Verification

Relative links and whitespace checks passed. Guides match API routes, schemas,
service validation, and integration tests. Runtime tests were not rerun for this
documentation-only change. Kevin's review completed RF-401.
