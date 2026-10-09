"""Explicit opt-in live embedding preparation; never called by ordinary tests."""

import argparse
import asyncio
import os
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.knowledge.langchain_embeddings import LangChainEmbeddingProvider
from api.knowledge.markdown import load_manifest, prepare_markdown
from api.knowledge.postgres_retriever import PostgresChunkIndexer
from api.knowledge.postgres_store import PostgresDocumentStore

ROOT = Path(__file__).resolve().parents[3]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Allow paid embedding API calls"
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("Explicit --live is required to generate provider embeddings")
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        parser.error("DATABASE_URL is required")
    documents = tuple(
        prepare_markdown(ROOT, meta)
        for meta in load_manifest(ROOT / "knowledge/manifest.json")
    )
    provider = LangChainEmbeddingProvider()
    engine = create_async_engine(make_url(raw).set(drivername="postgresql+psycopg"))
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        await PostgresDocumentStore(sessions).commit_batch(documents)
        count = await PostgresChunkIndexer(sessions, provider).index_documents(
            documents
        )
        print(f"Created {count} passage embeddings")
    finally:
        await engine.dispose()
        await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())
