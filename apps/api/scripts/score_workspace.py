"""Score fixture observations offline against frozen expectations; emit JSON."""

import argparse
import sys
from pathlib import Path

from api.evaluations.scoring import score_observations

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="JSON observations produced by evaluate_workspace.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="New JSON metrics file; never overwrite an existing report",
    )
    args = parser.parse_args()
    if args.output is not None and (
        args.output.exists() or not args.output.parent.is_dir()
    ):
        parser.error("Choose a new output file in an existing directory")
    try:
        report = score_observations(ROOT, args.input.read_bytes())
        output = report.model_dump_json(indent=2)
        if args.output is None:
            print(output)
        else:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(output + "\n")
    except Exception:
        print(
            "Metrics could not be produced; check observation schema, frozen labels, source provenance, and output location.",
            file=sys.stderr,
        )
        return 2
    return 1 if report.failed_checks or report.error_checks else 0


if __name__ == "__main__":
    raise SystemExit(main())
