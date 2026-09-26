# Issue-report extraction contract (RF-201)

The extractor's output is a proposed reading of a customer's issue report. It
does not verify that the reported events happened or diagnose their cause.

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

The four list fields may be empty. Every list item and the summary must contain
non-whitespace text. Unknown service and severity must be expressed as `null`,
not guessed. The service code is tentative until application code checks it.
The labels here define valid values; the rules for assigning severity are in
the [severity policy](severity-policy.md), and the rules for asking questions
are in the [clarification policy](clarification-policy.md).

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
