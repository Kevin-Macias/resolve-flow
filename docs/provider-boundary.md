# LLM provider boundary (RF-202)

Application code calls `LLMProvider.generate(instructions, input_text,
output_schema)` and receives `ProviderResult`. The optional Pydantic schema asks
the live provider for strict Structured Outputs; callers without one receive
ordinary raw text. The result contains either raw `text`, a `refusal`, or
neither when the provider returns empty output. It never contains both.

`OpenAIProvider` wraps the async OpenAI Responses API. Its model and optional
temperature and output-token cap are supplied by the caller. It requests `store=False`,
returns refusals separately from text, and turns SDK or incomplete-response
failures into `ProviderError`. With a schema, it sends its JSON Schema through
the Responses API `text.format` strict JSON schema setting. It is constructed
only when a real call is needed and requires normal OpenAI SDK credentials then.
Completed responses also expose input, output, and total token counts when the
API supplies usage.

`FakeProvider` returns a configured result and records calls. Ordinary tests use
it or an injected SDK stub and never call a live model. No route or extraction
workflow invokes either provider yet.

This boundary deliberately returns raw output. `extract_issue_report` validates
that output again against the application model. It returns a validated result
and per-call prompt/model record, or a typed error carrying that record. It
retries classified transient provider failures under a [bounded policy](retry-policy.md).
It does not enforce severity or clarification policy in application code or
record usage. Those behaviors have later roadmap tickets.
