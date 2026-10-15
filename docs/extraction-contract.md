# Issue-report extraction contract (RF-201)

The extractor proposes an interpretation of the customer's report. Its claims
remain unverified and its output is not a diagnosis.

`ExtractionResult` has these required fields:

| Field | Meaning |
| --- | --- |
| `summary` | Short, non-empty paraphrase of the report |
| `service_code` | Tentative service code, or `null` when unknown |
| `severity` | Tentative `low`, `medium`, `high`, or `critical`; `null` when impact is unknown |
| `confidence` | `low`, `medium`, or `high` confidence in interpreting the report, not in the truth of its claims |
| `reported_facts` | Non-empty statements attributed to the customer; not verified evidence |
| `missing_data` | Information still needed to understand the report |
| `contradictions` | Conflicting customer statements that need clarification; may be empty |
| `questions` | Questions proposed for the customer |

Lists may be empty; each item and the summary must contain non-whitespace text.
Use `null` for unknown service or severity. Application code checks the tentative
service code. See the [severity policy](severity-policy.md) for classification
rules and the [clarification policy](clarification-policy.md) for questions.

Example for “Payments sometimes remain pending after a successful Stripe
checkout”:

```json
{
  "summary": "Payments sometimes remain pending after checkout",
  "service_code": "payments",
  "severity": null,
  "confidence": "low",
  "reported_facts": [
    "Customer reports pending payments after successful Stripe checkout"
  ],
  "missing_data": ["Number of affected payments", "When the issue began"],
  "contradictions": [],
  "questions": ["How many payments have remained pending, and since when?"]
}
```

The contract is a Pydantic model in `apps/api/src/api/extraction/schemas.py`.
RF-203 sends this model as the requested Structured Outputs schema, then
validates returned JSON locally before using it. Schema adherence does not
verify the customer's claims or the model's interpretation.
