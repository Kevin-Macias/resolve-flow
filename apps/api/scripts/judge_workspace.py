"""Judge approved extraction observations; offline by default, live judging opt-in."""

import argparse
import asyncio
import math
import os
import sys
from pathlib import Path

from api.evaluations.judge_contracts import JudgeMethod
from api.evaluations.judging import FixtureJudge, judge_observations
from api.extraction.provider import LLMProvider, OpenAIProvider

ROOT = Path(__file__).resolve().parents[3]


def positive_timeout(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("Timeout must be finite and positive")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--judge", choices=("fixture", "openai"), default="fixture")
    parser.add_argument("--allow-live-judge", action="store_true")
    parser.add_argument("--model", help="Explicit judge model/version; no default")
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--timeout-seconds", type=positive_timeout, default=60)
    args = parser.parse_args()
    if args.max_output_tokens <= 0:
        parser.error("Max output tokens must be positive")
    if args.output is not None and (
        args.output.exists() or not args.output.parent.is_dir()
    ):
        parser.error("Choose a new output file in an existing directory")
    method: JudgeMethod = "openai" if args.judge == "openai" else "fixture"
    if method == "openai" and (
        not args.allow_live_judge
        or not args.model
        or not args.model.strip()
        or not os.environ.get("OPENAI_API_KEY")
    ):
        parser.error(
            "Live judging requires --allow-live-judge, --model, and OPENAI_API_KEY"
        )
    if method == "fixture" and (args.allow_live_judge or args.model):
        parser.error("Live judge options require --judge openai")
    try:
        # Validate the input before constructing a provider or making any calls.
        from api.evaluations.scoring import validated_observations

        raw = args.input.read_bytes()
        validated_observations(ROOT, raw)
        provider: LLMProvider = (
            OpenAIProvider(args.model, max_output_tokens=args.max_output_tokens)
            if method == "openai"
            else FixtureJudge()
        )
        report = asyncio.run(
            judge_observations(
                ROOT, raw, provider, method=method, timeout_seconds=args.timeout_seconds
            )
        )
        output = report.model_dump_json(indent=2)
        if args.output is None:
            print(output)
        else:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(output + "\n")
    except Exception:
        print(
            "Judgments could not be produced; check input provenance, judge configuration, and output location.",
            file=sys.stderr,
        )
        return 2
    return 1 if report.failed_checks or report.error_checks else 0


if __name__ == "__main__":
    raise SystemExit(main())
