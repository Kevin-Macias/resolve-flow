# Updating the affected service on an issue report

Intended visibility: INTERNAL. Source version: 1. Authored: 2026-10-06.

## Applicability

Use when the affected service is incorrect or needs to be cleared on an existing,
visible report. Current API behavior.

## Checks and behavior

Omitting `affected_service_code` from a PATCH leaves it unchanged. Supplying a
known service code changes the association; supplying null clears it. An unknown
service code returns HTTP 422. The customer update contract does not permit
editing the description or status.

## Limits

A service update does not change account ownership, archive status, or customer
list visibility. Missing, archived, and other-account reports are unavailable
through this update route. This guide mentions issue reports and validation but
does not diagnose a report missing from the customer's list.
