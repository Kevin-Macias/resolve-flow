"""LangChain provider integration; domain evidence contracts remain independent."""

import asyncio

from langchain_openai import OpenAIEmbeddings
from openai import APITimeoutError, AsyncOpenAI, OpenAI

from api.knowledge.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_PROFILE,
    EmbeddingError,
    EmbeddingFailure,
    validate_input,
)


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
                async_client=self._async_client.embeddings
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
        try:
            return await self._client.aembed_documents(list(texts))
        except APITimeoutError:
            raise EmbeddingError(EmbeddingFailure.TIMEOUT) from None
        except Exception:
            raise EmbeddingError(EmbeddingFailure.UNAVAILABLE) from None

    async def embed_query(self, text: str) -> list[float]:
        validate_input(text)
        try:
            return await self._client.aembed_query(text)
        except APITimeoutError:
            raise EmbeddingError(EmbeddingFailure.TIMEOUT) from None
        except Exception:
            raise EmbeddingError(EmbeddingFailure.UNAVAILABLE) from None
