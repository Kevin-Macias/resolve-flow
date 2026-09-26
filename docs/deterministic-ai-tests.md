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

The fake responses are chosen test inputs. These tests verify schema handling,
error mapping, and retry boundaries; they do not measure whether a live model
would choose the right severity or ask the right question. RF-209 covers opt-in
live model checks, and later evaluation tickets measure classification quality.
