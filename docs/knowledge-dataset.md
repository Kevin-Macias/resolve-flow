# Curated knowledge dataset (RF-401)

Status: DONE. Kevin approved the issue-report submission and visibility scope
and completed the PAIR review of the eight-document [corpus](../knowledge/README.md).

## Goal

Provide reference material for “I submitted an issue report, but I can't find
it in my list.” The [feature summary](issue-report-troubleshooting.md) records
existing behavior and separates it from planned frontend behavior.

Current guides describe actual API behavior. Sample investigations are fictional.
Superseded advice is explicitly an invented legacy fixture, not repository history.

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

RF-401 authors reference material. Retrieval, evaluation expectations, and
report recovery remain separate work. Kevin reviewed the completed corpus. No runtime code changes are proposed.

## Verification

Checked relative Markdown links and whitespace integrity. Current behavior was
compared with the API routes, schemas, service validation, and existing integration
test cases. No runtime code changed; runtime tests were not rerun. RF-401 is DONE following Kevin's review of the completed sources.
