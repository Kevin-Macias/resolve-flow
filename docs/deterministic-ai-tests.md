# Deterministic extraction scenarios (RF-208)

`apps/api/tests/extraction/test_ai_scenarios.py` runs six customer-report
scenarios with fake providers. The normal test suite does not need API
credentials or a live model.

| Scenario | Expected application behavior |
| --- | --- |
| Team cannot submit invoices | Preserve the fake provider's tentative `medium` severity and reported facts. |
| Payments sometimes pending | Preserve `null` severity when impact is unclear. |
| “Something broke, maybe exports” | Preserve unknown service/severity and low interpretation confidence. |
| Malformed model text | Return `malformed_json` after one attempt. |
| Model refusal | Return `refusal` after one attempt. |
| Hanging provider | End at the configured timeout and report a timeout failure. |

Fake responses test schema handling, errors, and retry limits. Live severity
and question quality remain unmeasured. RF-209 checks live integration; later
evaluations measure classification quality.
