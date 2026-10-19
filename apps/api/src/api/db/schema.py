"""Read the migration contract shipped with this API build."""

import os
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


def migration_config() -> Config:
    root = Path(os.getenv("RESOLVEFLOW_API_ROOT", Path(__file__).resolve().parents[3]))
    return Config(str(root / "alembic.ini"))


@lru_cache(maxsize=1)
def expected_heads() -> tuple[str, ...]:
    heads = tuple(sorted(ScriptDirectory.from_config(migration_config()).get_heads()))
    if not heads:
        raise RuntimeError("Migration history is missing")
    return heads


def checkpoint_version() -> int:
    return len(AsyncPostgresSaver.MIGRATIONS) - 1
