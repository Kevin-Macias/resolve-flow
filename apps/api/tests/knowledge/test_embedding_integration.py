import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain_openai import OpenAIEmbeddings

from api.knowledge.chunks import PreparedChunk, prepare_chunks
from api.knowledge.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_PROFILE,
    EmbeddingError,
    EmbeddingFailure,
    embed_documents_checked,
    embed_query_checked,
    input_token_count,
    validate_input,
    validate_vector,
)
from api.knowledge.langchain_embeddings import LangChainEmbeddingProvider
from api.knowledge.markdown import load_manifest, parse_sections, prepare_markdown

ROOT = Path(__file__).resolve().parents[4]


def unit_vector() -> list[float]:
    return [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)


class TestEmbeddings:
    __test__ = False
    profile = "test:1536:v1"

    def __init__(
        self, vectors: list[list[float]] | None = None, failure: Exception | None = None
    ) -> None:
        self.vectors = vectors
        self.failure = failure
        self.document_calls: list[tuple[str, ...]] = []
        self.query_calls: list[str] = []

    async def embed_documents(self, texts: tuple[str, ...]) -> list[list[float]]:
        self.document_calls.append(texts)
        if self.failure:
            raise self.failure
        return (
            self.vectors if self.vectors is not None else [unit_vector() for _ in texts]
        )

    async def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        if self.failure:
            raise self.failure
        return self.vectors[0] if self.vectors is not None else unit_vector()


def test_corpus_chunks_budget_and_exact_locations() -> None:
    all_chunks: list[PreparedChunk] = []
    for metadata in load_manifest(ROOT / "knowledge/manifest.json"):
        document = prepare_markdown(ROOT, metadata)
        chunks = prepare_chunks(document)
        assert chunks == prepare_chunks(document)
        assert [c.ordinal for c in chunks] == list(range(len(chunks)))
        for chunk in chunks:
            location = chunk.passage.location
            assert location.kind == "markdown"
            lines = document.text.splitlines(keepends=True)
            assert chunk.text == "".join(
                lines[location.line_start - 1 : location.line_end]
            )
            assert chunk.embedding_input == metadata.title + "\n\n" + chunk.text
            assert chunk.metadata == metadata
        all_chunks.extend(chunks)
    assert len(all_chunks) == 31
    assert len({chunk.chunk_id for chunk in all_chunks}) == 31
    assert max(input_token_count(c.embedding_input) for c in all_chunks) == 127


def test_substantive_preamble_and_intro_are_retained() -> None:
    document = prepare_markdown(
        ROOT, load_manifest(ROOT / "knowledge/manifest.json")[0]
    )
    for text in (
        "A useful preamble.\n\n# Guide\n\nIntroductory advice.\n",
        "# Guide\n\nIntended visibility: INTERNAL.\n\nActual advice.\n",
    ):
        changed = document.model_copy(
            update={"text": text, "sections": parse_sections(text, document.metadata)}
        )
        chunks = prepare_chunks(changed)
        assert "".join(chunk.text for chunk in chunks) == text
    changed_version = prepare_markdown(
        ROOT, document.metadata.model_copy(update={"version": "2"})
    )
    assert {c.chunk_id for c in prepare_chunks(document)}.isdisjoint(
        c.chunk_id for c in prepare_chunks(changed_version)
    )


def test_tampered_sections_rejected() -> None:
    doc = prepare_markdown(ROOT, load_manifest(ROOT / "knowledge/manifest.json")[0])
    altered = doc.sections[0].model_copy(update={"text": "invented passage"})
    with pytest.raises(EmbeddingError):
        prepare_chunks(
            doc.model_copy(update={"sections": (altered,) + doc.sections[1:]})
        )


def test_budget_rejects_without_truncation_and_special_tokens_are_plain_text() -> None:
    validate_input(" hello" * 512)
    validate_input("<|endoftext|> appears in untrusted source text")
    with pytest.raises(EmbeddingError) as error:
        validate_input(" hello" * 513)
    assert error.value.reason == EmbeddingFailure.INPUT_TOO_LONG
    for text in ("", " "):
        with pytest.raises(EmbeddingError):
            validate_input(text)
    provider = TestEmbeddings()
    with pytest.raises(EmbeddingError):
        asyncio.run(embed_documents_checked(provider, ("hello", " hello" * 513)))
    assert provider.document_calls == []
    doc = prepare_markdown(ROOT, load_manifest(ROOT / "knowledge/manifest.json")[0])
    text = "# Too long\n\n" + " hello" * 513
    with pytest.raises(EmbeddingError):
        prepare_chunks(
            doc.model_copy(
                update={"text": text, "sections": parse_sections(text, doc.metadata)}
            )
        )


@pytest.mark.parametrize(
    "vector",
    [[1.0], [0.0] * 1536, [float("nan")] * 1536, [float("inf")] * 1536, [1e39] * 1536],
)
def test_invalid_vector_rejected(vector: list[float]) -> None:
    with pytest.raises(EmbeddingError) as error:
        validate_vector(vector)
    assert error.value.reason == EmbeddingFailure.INVALID_RESPONSE


def test_embedding_count_and_empty_batch() -> None:
    provider = TestEmbeddings(vectors=[unit_vector()])
    with pytest.raises(EmbeddingError):
        asyncio.run(embed_documents_checked(provider, ("one", "two")))
    assert asyncio.run(embed_documents_checked(provider, ())) == ()
    assert len(provider.document_calls) == 1
    assert asyncio.run(embed_query_checked(provider, "query")) == unit_vector()


@pytest.mark.parametrize(
    "failure,reason",
    [
        (TimeoutError("secret"), EmbeddingFailure.TIMEOUT),
        (RuntimeError("secret"), EmbeddingFailure.UNAVAILABLE),
    ],
)
def test_embedding_errors_sanitized(
    failure: Exception, reason: EmbeddingFailure
) -> None:
    provider = TestEmbeddings(failure=failure)
    for operation in (
        embed_documents_checked(provider, ("text",)),
        embed_query_checked(provider, "text"),
    ):
        with pytest.raises(EmbeddingError) as error:
            asyncio.run(operation)
        assert error.value.reason == reason
        assert "secret" not in str(error.value)
        assert error.value.__suppress_context__


def test_langchain_delegation_with_no_network_and_config_validation() -> None:
    response = {"data": [{"embedding": unit_vector()}]}
    client = AsyncMock()
    client.create.return_value = response
    settings: dict[str, Any] = {
        "model": "text-embedding-3-small",
        "dimensions": 1536,
        "check_embedding_ctx_length": False,
        "async_client": client,
        "api_key": "offline-fixture",
        "max_retries": 0,
        "timeout": 30,
    }
    adapter = LangChainEmbeddingProvider(OpenAIEmbeddings(**settings))
    assert adapter.profile == EMBEDDING_PROFILE
    assert asyncio.run(embed_documents_checked(adapter, ("exact text\n",))) == (
        unit_vector(),
    )
    assert asyncio.run(embed_query_checked(adapter, "query")) == unit_vector()
    calls = client.create.call_args_list
    assert calls[0].kwargs["input"] == ["exact text\n"]
    assert calls[1].kwargs["input"] == ["query"]
    assert calls[0].kwargs["model"] == "text-embedding-3-small"
    assert calls[0].kwargs["dimensions"] == 1536
    client.create.side_effect = RuntimeError("secret")
    with pytest.raises(EmbeddingError) as error:
        asyncio.run(adapter.embed_query("query"))
    assert error.value.reason == EmbeddingFailure.UNAVAILABLE
    changes_list: tuple[dict[str, Any], ...] = (
        {"dimensions": 3072},
        {"model": "text-embedding-3-large"},
        {"check_embedding_ctx_length": True},
    )
    for changes in changes_list:
        with pytest.raises(EmbeddingError):
            LangChainEmbeddingProvider(OpenAIEmbeddings(**(settings | changes)))
    asyncio.run(adapter.aclose())


def test_owned_client_configuration_and_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "offline-fixture")
    provider = LangChainEmbeddingProvider()
    assert provider.profile == EMBEDDING_PROFILE
    asyncio.run(provider.aclose())
