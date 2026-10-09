"""Opt-in query embedding baseline over an already indexed trusted corpus."""

import argparse
import asyncio
import os
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.knowledge.embeddings import EMBEDDING_PROFILE, EmbeddingError
from api.knowledge.evaluation import evaluate_retrieval, load_cases
from api.knowledge.langchain_embeddings import LangChainEmbeddingProvider
from api.knowledge.markdown import load_manifest, prepare_markdown
from api.knowledge.postgres_retriever import PostgresRetriever, verify_indexed_corpus

ROOT = Path(__file__).resolve().parents[3]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Allow paid query embedding calls"
    )
    parser.add_argument(
        "--output", type=Path, help="Write the internal JSON report to this new file"
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("Explicit --live is required to evaluate provider relevance")
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        parser.error("DATABASE_URL is required")
    if args.output is not None and args.output.exists():
        parser.error("Choose a new output file; existing reports are not overwritten")
    if args.output is not None and not args.output.parent.is_dir():
        parser.error("Output parent directory must exist")
    sources = tuple(
        prepare_markdown(ROOT, meta)
        for meta in load_manifest(ROOT / "knowledge/manifest.json")
    )
    cases = load_cases(ROOT / "knowledge/evaluations/retrieval-v1.json")
    engine = create_async_engine(make_url(raw).set(drivername="postgresql+psycopg"))
    provider: LangChainEmbeddingProvider | None = None
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await verify_indexed_corpus(sessions, sources, EMBEDDING_PROFILE)
        except EmbeddingError as error:
            parser.error(
                f"Baseline setup failed: {error.reason.value}; verify indexing before retrying"
            )
        provider = LangChainEmbeddingProvider()
        report = await evaluate_retrieval(
            PostgresRetriever(sessions, provider),
            cases,
            sources,
            embedding_profile=provider.profile,
            run_mode="live",
        )
        output = report.model_dump_json(indent=2)
        if args.output is None:
            print(output)
        else:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(output + "\n")
            print(f"Wrote {len(report.cases)} case results")
        if (
            report.failed_cases
            or report.observed_exclusion_violations
            or report.observed_duplicate_chunks
        ):
            raise SystemExit(1)
    finally:
        await engine.dispose()
        if provider is not None:
            await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())
