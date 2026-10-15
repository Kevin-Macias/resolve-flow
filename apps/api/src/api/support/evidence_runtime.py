"""Explicit offline/live support analysis adapters and trusted corpus loading."""

import asyncio
import os
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.extraction.provider import LLMProvider, OpenAIProvider
from api.knowledge.chunks import prepare_chunks
from api.knowledge.citations import (
    CitationReport,
    ClaimDraft,
    ClaimKind,
    EvidenceReference,
)
from api.knowledge.evidence_analysis import (
    EvidenceAnalysisInput,
    EvidenceAnalysisOutput,
    build_evidence_analysis_input,
    validate_evidence_analysis_output,
)
from api.knowledge.fake_retriever import FakeRetriever
from api.knowledge.langchain_embeddings import LangChainEmbeddingProvider
from api.knowledge.markdown import MarkdownDocument, load_manifest, prepare_markdown
from api.knowledge.metadata import KnowledgeContract, Text
from api.knowledge.postgres_retriever import PostgresRetriever, verify_indexed_corpus
from api.knowledge.retrieval import (
    EvidenceCandidate,
    RetrievalRequest,
    RetrievalResult,
    RetrievalService,
)


class AnalysisProvider(Protocol):
    async def analyze(self, value: EvidenceAnalysisInput) -> str: ...


class LiveClaim(KnowledgeContract):
    # Strict provider schemas require nullable/defaulted fields to be explicit.
    claim_id: Text
    statement: Text
    kind: ClaimKind
    explanation: Text | None
    references: tuple[EvidenceReference, ...]


class LiveAnalysisOutput(KnowledgeContract):
    claims: tuple[LiveClaim, ...]


class OfflineAnalysisProvider:
    async def analyze(self, value: EvidenceAnalysisInput) -> str:
        # A scripted gap never invents a diagnosis from a fixture ranking.
        return EvidenceAnalysisOutput(
            claims=(
                ClaimDraft(
                    claim_id="simulation-gap",
                    statement="The cause of this report's problem has not been established.",
                    kind=ClaimKind.MISSING_EVIDENCE,
                    explanation="Offline simulation shows source passages, not a semantic diagnosis. Review the observations and sources.",
                ),
            )
        ).model_dump_json()


class LiveAnalysisProvider:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def analyze(self, value: EvidenceAnalysisInput) -> str:
        result = await self.provider.generate(
            value.instructions, value.input_json, LiveAnalysisOutput
        )
        if result.refusal is not None or not result.text:
            raise ValueError("Analysis did not produce a valid result")
        return result.text


class EvidenceRuntime:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def sources(self) -> tuple[MarkdownDocument, ...]:
        def load() -> tuple[MarkdownDocument, ...]:
            root = Path(
                os.getenv("KNOWLEDGE_ROOT") or str(Path(__file__).resolve().parents[5])
            )
            return tuple(
                prepare_markdown(root, meta)
                for meta in load_manifest(root / "knowledge/manifest.json")
            )

        return await asyncio.to_thread(load)

    def mode(self) -> str:
        mode = os.getenv("EVIDENCE_PROVIDER_MODE", "offline")
        if mode not in ("offline", "live"):
            raise ValueError("Unsupported evidence provider mode")
        return mode

    async def generate(
        self,
        request: RetrievalRequest,
        sources: tuple[MarkdownDocument, ...],
        mode: str,
    ) -> tuple[RetrievalResult, CitationReport]:
        async with asyncio.timeout(60):
            if mode == "offline":
                candidates = tuple(
                    EvidenceCandidate(
                        chunk_id=chunk.chunk_id,
                        text=chunk.text,
                        metadata=chunk.metadata,
                        passage=chunk.passage,
                        score=0.5,
                        score_metric="fixture",
                    )
                    for source in sources
                    for chunk in prepare_chunks(source)
                )
                result = await RetrievalService(FakeRetriever(candidates)).search(
                    request
                )
                analysis = await OfflineAnalysisProvider().analyze(
                    build_evidence_analysis_input(request, result, sources)
                )
            else:
                # Clients are created only for an explicit live POST, never on GET.
                model = os.environ["EVIDENCE_OPENAI_MODEL"]
                embedding = LangChainEmbeddingProvider()
                provider: OpenAIProvider | None = None
                try:
                    provider = OpenAIProvider(model, max_output_tokens=4000)
                    await verify_indexed_corpus(
                        self.sessions, sources, embedding.profile
                    )
                    result = await RetrievalService(
                        PostgresRetriever(self.sessions, embedding)
                    ).search(request)
                    analysis = await LiveAnalysisProvider(provider).analyze(
                        build_evidence_analysis_input(request, result, sources)
                    )
                finally:
                    try:
                        if provider is not None:
                            await provider.client.close()
                    finally:
                        await embedding.aclose()
            return result, validate_evidence_analysis_output(
                analysis, request, result, sources
            )
