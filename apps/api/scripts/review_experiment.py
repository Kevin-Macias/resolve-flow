"""Render an RF-607 experiment and optional human review; never make provider calls."""

import argparse
import sys
from pathlib import Path

from api.evaluations.experiment_report import render_experiment
from api.evaluations.experiment_review import (
    load_experiment,
    load_review,
    review_template,
)

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review-template", type=Path)
    args = parser.parse_args()
    outputs = [p for p in (args.output, args.review_template) if p is not None]
    if len({p.resolve() for p in outputs}) != len(outputs) or any(
        p.exists() or not p.parent.is_dir() for p in outputs
    ):
        parser.error("Choose distinct new output files in existing directories")
    try:
        raw = args.input.read_bytes()
        report = load_experiment(ROOT, raw)
        review = (
            load_review(report, raw, args.review.read_bytes())
            if args.review
            else review_template(report, raw)
        )
        result = render_experiment(report, review)
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(result)
        else:
            print(result, end="")
        if args.review_template:
            with args.review_template.open("x", encoding="utf-8") as stream:
                stream.write(
                    review_template(report, raw).model_dump_json(indent=2) + "\n"
                )
    except Exception:
        print(
            "Review could not be produced; check experiment/review provenance and output locations.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
