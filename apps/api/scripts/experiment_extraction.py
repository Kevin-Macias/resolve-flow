"""Run the approved 12-call RF-607 live extraction comparison into a new directory."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from api.evaluations.experiment import run_experiment
from api.evaluations.experiment_contracts import ExperimentReport
from api.evaluations.experiment_prompt import prompts
from api.evaluations.experiment_report import render_experiment
from api.evaluations.experiment_review import load_experiment, review_template
from api.extraction.provider import OpenAIProvider

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL"))
    parser.add_argument(
        "--reasoning-effort",
        choices=("none", "low", "medium", "high", "xhigh", "max"),
        default=os.environ.get("OPENAI_REASONING_EFFORT", "low"),
    )
    args = parser.parse_args()
    if (
        not args.allow_live
        or not args.model
        or not args.model.strip()
        or not os.environ.get("OPENAI_API_KEY")
    ):
        parser.error("Requires --allow-live, a model, and OPENAI_API_KEY")
    if args.reasoning_effort not in ("none", "low", "medium", "high", "xhigh", "max"):
        parser.error("Invalid reasoning effort")
    if args.output_dir.exists() or not args.output_dir.parent.is_dir():
        parser.error("Choose a new output directory in an existing parent")
    try:
        prompts()
        args.output_dir.mkdir(mode=0o700)

        def persist(report: ExperimentReport) -> None:
            temporary = args.output_dir / "experiment.tmp"
            temporary.write_text(
                report.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            temporary.replace(args.output_dir / "experiment.json")

        provider = OpenAIProvider(
            args.model,
            max_output_tokens=2048,
            reasoning_effort=args.reasoning_effort,
        )
        report = asyncio.run(
            run_experiment(ROOT, provider, mode="live", progress=persist)
        )
        raw = (args.output_dir / "experiment.json").read_bytes()
        load_experiment(ROOT, raw)
        review = review_template(report, raw)
        (args.output_dir / "review.json").write_text(
            review.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (args.output_dir / "comparison.md").write_text(
            render_experiment(report, review), encoding="utf-8"
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        print(
            "Experiment cancelled; retained progress must not be automatically retried.",
            file=sys.stderr,
        )
        return 130
    except Exception:
        print(
            "Experiment could not finish; inspect retained progress and configuration. No automatic retry was performed.",
            file=sys.stderr,
        )
        return 2
    return (
        1
        if any(
            c.status == "error" or any(k.status in ("fail", "error") for k in c.checks)
            for c in report.cases
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
