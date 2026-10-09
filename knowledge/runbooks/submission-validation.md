# Issue-report submission rejected by validation

Intended visibility: INTERNAL. Source version: 1. Authored: 2026-10-06.

## Applicability

Use when a customer says a newly submitted report is missing and there is a
recorded HTTP 422 response for the creation attempt. Current API behavior.

## Checks

Ask for the approximate submission time, the error shown, and whether a report
ID was returned. Do not ask for credentials. If an authorized response record
is available, check whether it belongs to that same attempt.

The description is trimmed and must contain 1–5,000 characters. An empty or
whitespace-only description is invalid. An affected service code is optional;
if provided, it must identify a known service. Extra creation fields are rejected.

## Interpretation

A validation rejection means that creation attempt did not create a report.
A successful creation returns HTTP 201 with a report ID and `submitted` status.
A customer remembering a click does not establish which response was returned.

## Next steps and limits

For a confirmed rejection, explain the specific validation issue and ask the
customer to correct it before submitting again. If the response was lost, do
not assume creation failed or recommend repeated submissions as a guaranteed
fix. Escalate the unknown outcome for investigation. This guide does not explain
why a report with confirmed successful creation later disappeared.
