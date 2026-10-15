"""Explicit offline script for exercising intake; no inference claim."""

import json
from typing import cast

from pydantic import BaseModel

from api.extraction.provider import ModelSettings, ProviderResult
from api.extraction.schemas import Confidence, ExtractionResult, Severity


class OfflineIntakeProvider:
    settings = ModelSettings(model="offline-intake-v1")

    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        # The graph serializes accepted turns only after a clarification answer.
        try:
            data: object = json.loads(input_text)
        except ValueError:
            data = None
        turns: object = (
            cast(dict[str, object], data).get("clarification_turns")
            if isinstance(data, dict)
            else None
        )
        answered = isinstance(turns, list) and bool(cast(list[object], turns))
        result = ExtractionResult(
            summary="Offline demonstration issue report",
            service_code="issue-reports",
            severity=Severity.LOW,
            confidence=Confidence.HIGH,
            reported_facts=[],
            contradictions=[],
            missing_data=[] if answered else ["Demonstration clarification"],
            questions=[]
            if answered
            else ["What happened, and what did you expect to happen?"],
        )
        return ProviderResult(text=result.model_dump_json())
