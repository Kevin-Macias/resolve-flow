"""Application embedding contract, input budget, and vector validation."""

import math
from enum import StrEnum
from typing import Protocol

import tiktoken

EMBEDDING_DIMENSIONS = 1536
EMBEDDING_PROFILE = "openai:text-embedding-3-small:1536:v1"
EMBEDDING_MODEL = "text-embedding-3-small"
MAX_INPUT_TOKENS = 512


class EmbeddingFailure(StrEnum):
    INVALID_INPUT = "invalid_input"
    INPUT_TOO_LONG = "input_too_long"
    INVALID_RESPONSE = "invalid_response"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"


class EmbeddingError(ValueError):
    def __init__(self, reason: EmbeddingFailure) -> None:
        self.reason = reason
        super().__init__(f"Embedding preparation failed: {reason.value}")


class EmbeddingProvider(Protocol):
    @property
    def profile(self) -> str: ...

    async def embed_documents(self, texts: tuple[str, ...]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


def input_token_count(text: str) -> int:
    # Document instruction-like strings are ordinary text, including special tokens.
    encoding = tiktoken.encoding_for_model(EMBEDDING_MODEL)
    return len(encoding.encode(text, disallowed_special=()))


def validate_input(text: str) -> None:
    if not text.strip():
        raise EmbeddingError(EmbeddingFailure.INVALID_INPUT)
    if input_token_count(text) > MAX_INPUT_TOKENS:
        raise EmbeddingError(EmbeddingFailure.INPUT_TOO_LONG)


def valid_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and abs(value) <= 3.4e38
    )


def validate_vector(vector: list[float]) -> list[float]:
    if len(vector) != EMBEDDING_DIMENSIONS or any(
        not valid_number(value) for value in vector
    ):
        raise EmbeddingError(EmbeddingFailure.INVALID_RESPONSE)
    result = [float(value) for value in vector]
    if math.hypot(*result) == 0:
        raise EmbeddingError(EmbeddingFailure.INVALID_RESPONSE)
    return result


def validate_profile(profile: str) -> None:
    if not profile.strip():
        raise EmbeddingError(EmbeddingFailure.INVALID_INPUT)


async def embed_documents_checked(
    provider: EmbeddingProvider, texts: tuple[str, ...]
) -> tuple[list[float], ...]:
    validate_profile(provider.profile)
    for text in texts:
        validate_input(text)
    if not texts:
        return ()
    try:
        vectors = await provider.embed_documents(texts)
        if len(vectors) != len(texts):
            raise EmbeddingError(EmbeddingFailure.INVALID_RESPONSE)
        return tuple(validate_vector(vector) for vector in vectors)
    except EmbeddingError as error:
        raise EmbeddingError(error.reason) from None
    except TimeoutError:
        raise EmbeddingError(EmbeddingFailure.TIMEOUT) from None
    except (TypeError, ValueError):
        raise EmbeddingError(EmbeddingFailure.INVALID_RESPONSE) from None
    except Exception:
        raise EmbeddingError(EmbeddingFailure.UNAVAILABLE) from None


async def embed_query_checked(provider: EmbeddingProvider, text: str) -> list[float]:
    validate_profile(provider.profile)
    validate_input(text)
    try:
        return validate_vector(await provider.embed_query(text))
    except EmbeddingError as error:
        raise EmbeddingError(error.reason) from None
    except TimeoutError:
        raise EmbeddingError(EmbeddingFailure.TIMEOUT) from None
    except (TypeError, ValueError):
        raise EmbeddingError(EmbeddingFailure.INVALID_RESPONSE) from None
    except Exception:
        raise EmbeddingError(EmbeddingFailure.UNAVAILABLE) from None
