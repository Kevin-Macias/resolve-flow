"""Explicit checkpoint schema initialization; never called on API startup."""

import asyncio
import os

from psycopg import Error

from api.workflow.checkpoints import setup_checkpoints


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("Set DATABASE_URL to initialize workflow checkpoints")
    try:
        asyncio.run(setup_checkpoints(database_url))
    except (Error, ValueError, RuntimeError):
        raise SystemExit(
            "Checkpoint setup failed; check database configuration and permissions"
        ) from None
    print("Workflow checkpoint schema is ready")


if __name__ == "__main__":
    main()
