"""Ingest trusted manifest sources into migrated PostgreSQL without model calls."""

import asyncio
import os
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.knowledge.postgres_store import PostgresDocumentStore, ingest_manifest_postgres

ROOT = Path(__file__).resolve().parents[3]


async def main() -> None:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        raise RuntimeError("DATABASE_URL is required for knowledge ingestion")
    engine = create_async_engine(make_url(raw).set(drivername="postgresql+psycopg"))
    try:
        store = PostgresDocumentStore(
            async_sessionmaker(engine, expire_on_commit=False)
        )
        results = await ingest_manifest_postgres(
            ROOT, ROOT / "knowledge/manifest.json", store
        )
        for result in results:
            print(f"{result.document_id}@{result.version}: {result.status.value}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
