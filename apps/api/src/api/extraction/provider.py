"""Application-owned boundary for raw model output."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    omit,
)
from pydantic import BaseModel

type ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class ProviderResult:
    text: str | None = None
    refusal: str | None = None
    usage: "ProviderUsage | None" = None

    def __post_init__(self) -> None:
        if self.text is not None and self.refusal is not None:
            raise ValueError("A provider result cannot contain text and a refusal")


class ProviderFailureKind(StrEnum):
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ProviderError(Exception):
    """The provider failed before producing usable output."""

    def __init__(
        self, message: str, kind: ProviderFailureKind = ProviderFailureKind.PERMANENT
    ) -> None:
        self.kind = kind
        super().__init__(message)


@dataclass(frozen=True)
class ModelSettings:
    model: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    reasoning_effort: ReasoningEffort | None = None


class LLMProvider(Protocol):
    settings: ModelSettings

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult: ...


class FakeProvider:
    def __init__(
        self, result: ProviderResult, settings: ModelSettings | None = None
    ) -> None:
        self.result = result
        self.settings = settings or ModelSettings(model="fake")
        self.calls: list[tuple[str, str, type[BaseModel] | None]] = []

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        self.calls.append((instructions, input_text, output_schema))
        return self.result


class OpenAIProvider:
    def __init__(
        self,
        model: str,
        client: AsyncOpenAI | None = None,
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> None:
        self.settings = ModelSettings(
            model, temperature, max_output_tokens, reasoning_effort
        )
        self.client = client if client is not None else AsyncOpenAI()

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        try:
            response = await self.client.with_options(max_retries=0).responses.create(
                model=self.settings.model,
                instructions=instructions,
                input=input_text,
                store=False,
                temperature=self.settings.temperature
                if self.settings.temperature is not None
                else omit,
                max_output_tokens=self.settings.max_output_tokens
                if self.settings.max_output_tokens is not None
                else omit,
                reasoning={"effort": self.settings.reasoning_effort}
                if self.settings.reasoning_effort is not None
                else omit,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": output_schema.__name__,
                        "schema": output_schema.model_json_schema(),
                        "strict": True,
                    }
                }
                if output_schema is not None
                else omit,
            )
        except APITimeoutError as error:
            raise ProviderError(
                "OpenAI request timed out", ProviderFailureKind.TIMEOUT
            ) from error
        except APIConnectionError as error:
            raise ProviderError(
                "OpenAI connection failed", ProviderFailureKind.TRANSIENT
            ) from error
        except APIStatusError as error:
            retryable = error.status_code in (408, 409, 429) or error.status_code >= 500
            kind = (
                ProviderFailureKind.TRANSIENT
                if retryable
                else ProviderFailureKind.PERMANENT
            )
            raise ProviderError("OpenAI request failed", kind) from error
        except OpenAIError as error:
            raise ProviderError("OpenAI request failed") from error

        if response.status != "completed":
            raise ProviderError("OpenAI response was not completed")

        usage = (
            ProviderUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.total_tokens,
            )
            if response.usage is not None
            else None
        )

        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "refusal":
                        return ProviderResult(refusal=content.refusal, usage=usage)

        return ProviderResult(text=response.output_text or None, usage=usage)
