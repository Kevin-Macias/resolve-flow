# Opt-in live extraction check (RF-209)

Add `OPENAI_API_KEY` and `OPENAI_MODEL=gpt-6-luna` to the ignored root `.env`
file (see `.env.example`). Set `OPENAI_REASONING_EFFORT=low` to make the chosen
effort explicit; low is also the command default. Do not put a real key in
`.env.example`. Then run from the
repository root:

```bash
pnpm test:live
```

The command loads the root `.env` and runs one synthetic invoice extraction
with the configured model, reasoning effort, and an 800-output-token cap.
The usual timeout and retry limits apply. Missing credentials or model selection
stop the check before a call. Run it separately from `pnpm check` and pytest.

The command prints one JSON record with schema validity, field names, counts,
elapsed milliseconds, attempt count, prompt ID/version, model name, and input,
output, and total tokens. It exits nonzero on an extraction failure or missing
usage. Report text and generated prose stay private. The check verifies
integration and schema shape, without exact-wording assertions. Classification
quality requires later evaluation.

The report is printed to the terminal and is not persisted by ResolveFlow.
`apps/api/tests/extraction/test_live_check_report.py` verifies the reporting
logic with a fake provider in the default suite.
