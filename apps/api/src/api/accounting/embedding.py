"""Capture each real embedding HTTP request before LangChain drops its usage."""

from typing import Any, cast

from pydantic import BaseModel, ValidationError

from api.accounting.contracts import Usage
from api.accounting.recording import active
from api.extraction.provider import ProviderResult, ProviderUsage
from api.knowledge.embeddings import EMBEDDING_MODEL


class EmbeddingEndpoint:
    def __init__(self, endpoint: Any):
        self.endpoint = endpoint

    async def create(self, **kwargs: Any) -> Any:
        recorder = active.get()
        if recorder is None:
            return await self.endpoint.create(**kwargs)
        response: Any = None

        async def invoke() -> ProviderResult:
            nonlocal response
            response = await self.endpoint.create(**kwargs)
            data = (
                response.model_dump() if isinstance(response, BaseModel) else response
            )
            usage = None
            model = None
            if isinstance(data, dict):
                data = cast(dict[str, object], data)
                model = data.get("model")
                raw = data.get("usage")
                if isinstance(raw, dict):
                    raw = cast(dict[str, object], raw)
                    try:
                        valid = Usage.model_validate(
                            {
                                "input_tokens": raw.get("prompt_tokens"),
                                "output_tokens": 0,
                                "total_tokens": raw.get("total_tokens"),
                                "cached_input_tokens": 0,
                            }
                        )
                        usage = ProviderUsage(valid.input_tokens, 0, valid.total_tokens)
                    except ValidationError:
                        pass
            return ProviderResult(
                usage=usage,
                resolved_model=model if isinstance(model, str) else None,
                cached_input_tokens=0,
            )

        await recorder.call(
            invoke, "embedding", EMBEDDING_MODEL, None, None, independent=True
        )
        return response
