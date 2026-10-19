"""LangChain provider integration; domain evidence contracts remain independent."""

import asyncio
from uuid import uuid4

from langchain_openai import OpenAIEmbeddings
from openai import APITimeoutError, AsyncOpenAI, OpenAI

from api.accounting.embedding import EmbeddingEndpoint
from api.knowledge.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_PROFILE,
    EmbeddingError,
    EmbeddingFailure,
    validate_input,
)
from api.observability import trace


class LangChainEmbeddingProvider:
    def __init__(self, client: OpenAIEmbeddings | None = None) -> None:
        self._sync_client: OpenAI | None = None
        self._async_client: AsyncOpenAI | None = None
        if client is None:
            self._sync_client = OpenAI(max_retries=0, timeout=30)
            self._async_client = AsyncOpenAI(max_retries=0, timeout=30)
        self._client = (
            client
            if client is not None
            else OpenAIEmbeddings(
                model=EMBEDDING_MODEL,
                dimensions=EMBEDDING_DIMENSIONS,
                check_embedding_ctx_length=False,
                max_retries=0,
                timeout=30,
                chunk_size=32,
                client=self._sync_client.embeddings if self._sync_client else None,
                async_client=EmbeddingEndpoint(self._async_client.embeddings)
                if self._async_client
                else None,
            )
        )
        if (
            self._client.model != EMBEDDING_MODEL
            or self._client.dimensions != EMBEDDING_DIMENSIONS
            or self._client.check_embedding_ctx_length
        ):
            raise EmbeddingError(EmbeddingFailure.INVALID_INPUT)

    @property
    def profile(self) -> str:
        return EMBEDDING_PROFILE

    async def aclose(self) -> None:
        """Close owned SDK clients; an injected LangChain client stays caller-owned."""
        if self._async_client is not None:
            await self._async_client.close()
        if self._sync_client is not None:
            await asyncio.to_thread(self._sync_client.close)

    async def embed_documents(self, texts: tuple[str, ...]) -> list[list[float]]:
        for text in texts:
            validate_input(text)
        with trace(
            "model", component="embedding", call_id=uuid4(), error_code="provider"
        ) as span:
            try:
                return await self._client.aembed_documents(list(texts))
            except APITimeoutError:
                span.outcome = "timeout"
                span.failure_code = "timeout"
                raise EmbeddingError(EmbeddingFailure.TIMEOUT) from None
            except Exception:
                raise EmbeddingError(EmbeddingFailure.UNAVAILABLE) from None

    async def embed_query(self, text: str) -> list[float]:
        validate_input(text)
        with trace(
            "model", component="embedding", call_id=uuid4(), error_code="provider"
        ) as span:
            try:
                return await self._client.aembed_query(text)
            except APITimeoutError:
                span.outcome = "timeout"
                span.failure_code = "timeout"
                raise EmbeddingError(EmbeddingFailure.TIMEOUT) from None
            except Exception:
                raise EmbeddingError(EmbeddingFailure.UNAVAILABLE) from None
