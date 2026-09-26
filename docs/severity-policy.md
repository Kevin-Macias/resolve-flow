# Severity policy (RF-204)

This policy describes a **tentative** severity for a customer issue report. It
does not confirm an incident, its cause, or the full number of affected users.
Support reviews the report before treating the severity as confirmed.

## Rules

1. Use only impact and scope explicitly reported by the customer. Keep claims
   attributed to the customer. Do not infer a wider outage from a symptom,
   service name, urgency words, or the possible business importance of a feature.
2. If the report does not say enough about impact, use `null`. Do not use `low`
   as a fallback for missing information.
3. Choose the highest level whose impact is actually described. If two claims
   conflict, keep the classification tentative and surface the conflict for
   review rather than silently choosing the more severe interpretation.
4. Severity measures impact. `confidence` separately measures how clearly the
   report can be interpreted. A clear customer claim can have high extraction
   confidence while remaining unverified.
5. A reported data loss or security exposure needs prompt human review. The
   model's severity proposal must not become a verified incident statement or
   automatically trigger a consequential action.

## Levels

| Severity | Reported impact |
| --- | --- |
| `null` | Impact or affected scope is unclear. |
| `low` | Inconvenience or minor degradation; the core task still works, possibly through a workaround. |
| `medium` | One customer or team cannot complete a core task; broader impact has not been reported. |
| `high` | A major function is disrupted for multiple customers. |
| `critical` | A widespread outage, data loss, or security exposure is explicitly reported. |

## Examples

| Customer report | Tentative severity | Why |
| --- | --- | --- |
| “Payments sometimes remain pending after checkout.” | `null` | The report lacks affected scope and concrete outcome. |
| “Exports are slow, but retrying works.” | `low` | Degradation with a working path. |
| “Our team cannot submit invoices, and we have no workaround.” | `medium` | One team's core task is blocked. |
| “Several customer companies cannot complete checkout.” | `high` | Explicit multi-customer disruption of a major function. |
| “Checkout is down for all customers.” | `critical` | Explicit widespread outage claim. |
| “Our saved invoices disappeared after import, and we cannot recover them.” | `critical` | Explicit potential data loss; requires human review. |
| “I can see another customer's invoice.” | `critical` | Explicit potential security exposure; requires human review. |
| “This is urgent; the payment API timed out once.” | `null` | Urgency does not establish impact or scope. |

The versioned extraction prompt includes this ladder. Application code does not
yet enforce it, and clarification rules belong to later work.
