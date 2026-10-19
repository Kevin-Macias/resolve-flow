"""Render evaluation artifacts as Markdown; optionally compare a baseline, offline."""

import argparse
import sys
from pathlib import Path

from api.evaluations.report_inputs import load_report_inputs
from api.evaluations.reporting import render_report

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--baseline-observations", type=Path)
    parser.add_argument("--baseline-metrics", type=Path)
    parser.add_argument("--baseline-judgments", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if bool(args.baseline_observations) != bool(args.baseline_metrics) or (
        args.baseline_judgments and not args.baseline_observations
    ):
        parser.error(
            "A baseline needs both observations and metrics; judgments are optional"
        )
    if args.output is not None and (
        args.output.exists() or not args.output.parent.is_dir()
    ):
        parser.error("Choose a new output file in an existing directory")
    try:
        current = load_report_inputs(
            ROOT,
            args.observations.read_bytes(),
            args.metrics.read_bytes(),
            args.judgments.read_bytes() if args.judgments is not None else None,
        )
        baseline = (
            load_report_inputs(
                ROOT,
                args.baseline_observations.read_bytes(),
                args.baseline_metrics.read_bytes(),
                args.baseline_judgments.read_bytes()
                if args.baseline_judgments is not None
                else None,
            )
            if args.baseline_observations is not None
            else None
        )
        output = render_report(current, baseline)
        if args.output is None:
            print(output, end="")
        else:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(output)
    except Exception:
        print(
            "Report could not be produced; check artifact schemas, matching provenance, metric consistency, and output location.",
            file=sys.stderr,
        )
        return 2
    return (
        1
        if current.scores.failed_checks
        or current.scores.error_checks
        or (
            current.judge is not None
            and (current.judge.failed_checks or current.judge.error_checks)
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
