# Prompt and model settings (RF-205)

The issue-report extraction prompt lives in `apps/api/src/api/extraction/prompts.py`
as `EXTRACTION_PROMPT`. Its stable ID is `issue_report_extraction`; its current
version is `2`. Change the version when changing the instructions so later
evaluations can identify which instructions produced a result.

`OpenAIProvider` is configured with a model name and optional `temperature` and
`max_output_tokens`, and reasoning effort. An omitted optional setting uses the provider default.
The model is selected by the caller, not by the extraction service. The fake
provider uses model name `fake` unless a test supplies other settings.

`extract_issue_report` returns `ExtractionOutcome(result, call)` on success.
`call` records the prompt ID/version, output schema name, configured model
settings, number of attempts, and token usage when returned by the provider.
An `ExtractionError` carries the same record
for refusal, empty output, malformed JSON, invalid data, and provider failure.
This record is in memory only; persistent call history, latency, and cost
are planned for RF-705. No customer report text or model output is included in
the call record.
