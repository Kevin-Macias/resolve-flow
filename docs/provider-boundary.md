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

`FakeProvider` returns a configured result and records calls. Ordinary tests
use it or an SDK stub to stay offline. RF-202 adds the adapters; route and
workflow wiring are later integrations.

`extract_issue_report` validates raw provider output against the application
model. It returns a validated result or typed error, both with a prompt/model
record. Transient failures follow the [retry policy](retry-policy.md).
RF-202 leaves application severity/clarification enforcement and usage recording
to later tickets.
