# Resolved investigation: report disappeared after archival

Intended visibility: INTERNAL. Source version: 1. Authored: 2026-10-06.

## Fixture scope

Fictional historical investigation, dated 2026-09-10. Illustrative records below
are supplied fixture evidence, not a lookup feature implemented by the app.
The state observation illustrates the planned RF-512 support lookup.

## Customer observation

A customer said, “My submitted report disappeared from my list.”

## Recorded evidence

For fictional report R-DEMO-17 in fictional account A-DEMO, an authorized
creation response at 09:00 UTC was HTTP 201 with `submitted` status. A supplied
authorized state observation for the same report at 09:15 UTC showed `deleted`
status. A
customer read at 09:15 UTC returned HTTP 404 and the list omitted that report.
These labels are readable fixture identifiers, not valid API UUIDs.

## Confirmed finding

The same-report `deleted` state explains the disappearance under the current
[archive rules](../runbooks/archived-report.md). The 404 was consistent with that
finding but was not sufficient evidence on its own.

## Resolution and limits

Support explained archive behavior; the investigation was closed with no restore
performed. There is no customer restore operation. This example does not prove
that another missing report was archived, who archived it, when archival
occurred, or whether it was accidental.
