"""Opt-in live extraction check; never run from the default test suite."""

import asyncio
import os
from typing import cast

from api.extraction.live_check import format_live_report, inspect_extraction
from api.extraction.provider import OpenAIProvider, ReasoningEffort


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY to run the live extraction check")
    model = os.environ.get("OPENAI_MODEL")
    if not model:
        raise SystemExit("Set OPENAI_MODEL to run the live extraction check")
    effort = os.environ.get("OPENAI_REASONING_EFFORT", "low")
    if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise SystemExit("OPENAI_REASONING_EFFORT is not a supported value")

    provider = OpenAIProvider(
        model=model,
        max_output_tokens=800,
        reasoning_effort=cast(ReasoningEffort, effort),
    )
    report = asyncio.run(inspect_extraction(provider))
    print(format_live_report(report))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
