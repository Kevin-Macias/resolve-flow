"""Write or verify the OpenAPI snapshot used by the TypeScript client."""

import argparse
import json
import sys
from pathlib import Path

from api.main import create_app

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[3] / "packages/api-client/openapi.json"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rendered = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    output: Path = args.output
    if args.check:
        if not output.exists() or output.read_text() != rendered:
            print(f"OpenAPI snapshot is stale: {output}", file=sys.stderr)
            return 1
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
