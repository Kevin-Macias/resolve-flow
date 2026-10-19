"""Execute the reviewed fixture cases in isolated PostgreSQL schemas; emit JSON."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from api.evaluations.runner import run_evaluation

ROOT = Path(__file__).resolve().parents[3]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("EVALUATION_DATABASE_URL"),
        help="Explicit PostgreSQL database for temporary evaluation schemas",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="New JSON report file; never overwrite an existing report",
    )
    args = parser.parse_args()
    if not args.database_url:
        parser.error("Supply --database-url or EVALUATION_DATABASE_URL")
    if args.output is not None and (
        args.output.exists() or not args.output.parent.is_dir()
    ):
        parser.error("Choose a new output file in an existing directory")
    try:
        report = await run_evaluation(ROOT, args.database_url)
        output = report.model_dump_json(indent=2)
        if args.output is None:
            print(output)
        else:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(output + "\n")
    except Exception:
        print(
            "Evaluation could not complete; check the case artifact, source files, database access, and output location.",
            file=sys.stderr,
        )
        return 2
    return 1 if report.error_cases else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
