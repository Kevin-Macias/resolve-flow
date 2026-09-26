from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import httpx2
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    omit,
)

from api.extraction.provider import (
    FakeProvider,
    LLMProvider,
    ModelSettings,
    OpenAIProvider,
    ProviderError,
    ProviderFailureKind,
    ProviderResult,
    ProviderUsage,
)
from api.extraction.schemas import ExtractionResult


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def mock_client(
    response: object = None, error: Exception | None = None
) -> tuple[AsyncOpenAI, AsyncMock]:
    create = AsyncMock(return_value=response, side_effect=error)
    response_client = SimpleNamespace(create=create)
    client = cast(
        AsyncOpenAI,
        SimpleNamespace(
            responses=response_client,
            with_options=Mock(return_value=SimpleNamespace(responses=response_client)),
        ),
    )
    return client, create


async def call_provider(provider: LLMProvider) -> ProviderResult:
    return await provider.generate("Extract reported facts", "Payments are pending")


@pytest.mark.anyio
async def test_fake_provider_returns_configured_result_and_records_call() -> None:
    expected = ProviderResult(text='{"summary": "Payments pending"}')
    provider = FakeProvider(expected)

    assert await call_provider(provider) == expected
    assert provider.calls == [("Extract reported facts", "Payments are pending", None)]


@pytest.mark.anyio
async def test_openai_provider_maps_completed_text_without_live_call() -> None:
    client, create = mock_client(
        SimpleNamespace(
            status="completed", output=[], output_text="raw output", usage=None
        )
    )
    provider = OpenAIProvider(model="test-model", client=client)

    assert await call_provider(provider) == ProviderResult(text="raw output")
    cast(Mock, client.with_options).assert_called_once_with(max_retries=0)
    create.assert_awaited_once_with(
        model="test-model",
        instructions="Extract reported facts",
        input="Payments are pending",
        store=False,
        temperature=omit,
        max_output_tokens=omit,
        reasoning=omit,
        text=omit,
    )


@pytest.mark.anyio
async def test_openai_provider_requests_strict_structured_output() -> None:
    client, create = mock_client(
        SimpleNamespace(status="completed", output=[], output_text="{}", usage=None)
    )

    await OpenAIProvider("test-model", client).generate(
        "Extract", "Report", output_schema=ExtractionResult
    )

    assert create.await_args is not None
    assert create.await_args.kwargs["text"] == {
        "format": {
            "type": "json_schema",
            "name": "ExtractionResult",
            "schema": ExtractionResult.model_json_schema(),
            "strict": True,
        }
    }


@pytest.mark.anyio
async def test_openai_provider_sends_configured_model_settings() -> None:
    client, create = mock_client(
        SimpleNamespace(status="completed", output=[], output_text="{}", usage=None)
    )
    provider = OpenAIProvider(
        "test-model",
        client,
        temperature=0.2,
        max_output_tokens=400,
        reasoning_effort="high",
    )

    await call_provider(provider)

    assert provider.settings == ModelSettings("test-model", 0.2, 400, "high")
    assert create.await_args is not None
    assert create.await_args.kwargs["model"] == "test-model"
    assert create.await_args.kwargs["temperature"] == 0.2
    assert create.await_args.kwargs["max_output_tokens"] == 400
    assert create.await_args.kwargs["reasoning"] == {"effort": "high"}


@pytest.mark.anyio
async def test_openai_provider_maps_token_usage() -> None:
    response = SimpleNamespace(
        status="completed",
        output=[],
        output_text="{}",
        usage=SimpleNamespace(input_tokens=25, output_tokens=40, total_tokens=65),
    )
    client, _ = mock_client(response)

    result = await call_provider(OpenAIProvider("test-model", client))

    assert result.usage == ProviderUsage(25, 40, 65)


@pytest.mark.anyio
async def test_openai_provider_preserves_refusal() -> None:
    refusal = SimpleNamespace(type="refusal", refusal="Unable to comply")
    message = SimpleNamespace(type="message", content=[refusal])
    client, _ = mock_client(
        SimpleNamespace(
            status="completed", output=[message], output_text="", usage=None
        )
    )

    assert await call_provider(OpenAIProvider("test-model", client)) == ProviderResult(
        refusal="Unable to comply"
    )


@pytest.mark.anyio
async def test_openai_provider_keeps_empty_output_for_later_validation() -> None:
    client, _ = mock_client(
        SimpleNamespace(status="completed", output=[], output_text="", usage=None)
    )

    assert await call_provider(OpenAIProvider("test-model", client)) == ProviderResult()


@pytest.mark.anyio
async def test_openai_provider_rejects_incomplete_response() -> None:
    client, _ = mock_client(
        SimpleNamespace(
            status="incomplete", output=[], output_text="partial", usage=None
        )
    )

    with pytest.raises(ProviderError, match="not completed"):
        await call_provider(OpenAIProvider("test-model", client))


@pytest.mark.anyio
async def test_openai_provider_wraps_sdk_error() -> None:
    client, _ = mock_client(error=OpenAIError("SDK failure"))

    with pytest.raises(ProviderError, match="request failed"):
        await call_provider(OpenAIProvider("test-model", client))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status_code", "kind"),
    [
        (400, ProviderFailureKind.PERMANENT),
        (401, ProviderFailureKind.PERMANENT),
        (408, ProviderFailureKind.TRANSIENT),
        (409, ProviderFailureKind.TRANSIENT),
        (429, ProviderFailureKind.TRANSIENT),
        (500, ProviderFailureKind.TRANSIENT),
        (503, ProviderFailureKind.TRANSIENT),
    ],
)
async def test_openai_provider_classifies_http_errors(
    status_code: int, kind: ProviderFailureKind
) -> None:
    request = httpx2.Request("POST", "https://example.test/responses")
    response = httpx2.Response(status_code, request=request)
    client, _ = mock_client(
        error=APIStatusError("failed", response=response, body=None)
    )

    with pytest.raises(ProviderError) as error:
        await call_provider(OpenAIProvider("test-model", client))

    assert error.value.kind is kind


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("sdk_error", "kind"),
    [
        (
            APITimeoutError(httpx2.Request("POST", "https://example.test")),
            ProviderFailureKind.TIMEOUT,
        ),
        (
            APIConnectionError(request=httpx2.Request("POST", "https://example.test")),
            ProviderFailureKind.TRANSIENT,
        ),
    ],
)
async def test_openai_provider_classifies_transport_errors(
    sdk_error: Exception, kind: ProviderFailureKind
) -> None:
    client, _ = mock_client(error=sdk_error)

    with pytest.raises(ProviderError) as error:
        await call_provider(OpenAIProvider("test-model", client))

    assert error.value.kind is kind


def test_result_cannot_contain_both_text_and_refusal() -> None:
    with pytest.raises(ValueError):
        ProviderResult(text="output", refusal="no")
