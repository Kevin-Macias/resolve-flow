# Archived issue report absent from customer reads

Intended visibility: INTERNAL. Source version: 1. Authored: 2026-10-06.

## Applicability

Use when a report was previously created but is now absent from its account's
list or returns HTTP 404 on a customer read. Current API behavior.

## Checks

Collect the report ID and approximate times of creation and disappearance.
Ask whether the customer recalls archiving it. Customer recollection is an
observation, not confirmed archive completion.

The current support workflow cannot independently look up archived reports.
Record that limitation as an evidence gap. Do not infer archival from HTTP 404
or describe an unavailable audit check as a step support can perform.

RF-512 plans an authorized lookup of current report state. Once implemented,
that lookup can confirm `deleted` status within permitted account scope. It
will not establish who archived the report or when.

## Interpretation

Archiving sets status to `deleted` and retains the database row. Customer list
and read operations exclude that row. A missing, archived, or other-account
report can each produce HTTP 404; the response alone cannot identify the cause.

## Next steps and limits

Explain general archive behavior without implying physical deletion. There
is no customer restore operation, and changing the affected service cannot
restore visibility. If the report's current archive status cannot be established, keep the cause
uncertain and propose an investigation rather than claiming the report was
archived. Do not bypass account scope to search for the report.
