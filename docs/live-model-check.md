# Opt-in live extraction check (RF-209)

Add `OPENAI_API_KEY` and `OPENAI_MODEL=gpt-6-luna` to the ignored root `.env`
file (see `.env.example`). Set `OPENAI_REASONING_EFFORT=low` to make the chosen
effort explicit; low is also the command default. Do not put a real key in
`.env.example`. Then run from the
repository root:

```bash
pnpm test:live
```

This command loads the root `.env` file. It is separate from `pnpm check` and
ordinary pytest. It runs one
extraction with a fixed synthetic invoice report, using the configured
model and reasoning effort with a cap of 800 output tokens. The usual timeout and retry policy still
applies. Missing credentials or model selection stop before any model call.

The command prints one JSON record with schema validity, field names, counts,
elapsed milliseconds, attempt count, prompt ID/version, model name, and input,
output, and total tokens. It exits nonzero on an extraction failure or missing
usage. It does not print the customer report or generated prose, and it makes no
exact-wording assertion. A successful check confirms the integration path and
schema shape; it does not measure classification quality. That belongs to the
evaluation phase.

The report is printed to the terminal and is not persisted by ResolveFlow.
`apps/api/tests/extraction/test_live_check_report.py` verifies the reporting
logic with a fake provider in the default suite.
