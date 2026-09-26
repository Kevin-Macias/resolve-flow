"""Shape and usage report for an opt-in live extraction check."""

import json
from dataclasses import asdict
from time import monotonic
from typing import Any

from api.extraction.provider import LLMProvider
from api.extraction.schemas import ExtractionResult
from api.extraction.service import ExtractionError, extract_issue_report

SYNTHETIC_REPORT = (
    "Our team cannot submit invoices today. We see an error after pressing "
    "Submit, and we have no workaround."
)


async def inspect_extraction(provider: LLMProvider) -> dict[str, Any]:
    started = monotonic()
    try:
        outcome = await extract_issue_report(SYNTHETIC_REPORT, provider)
    except ExtractionError as error:
        return {
            "ok": False,
            "model": error.call.model_settings.model,
            "prompt_id": error.call.prompt_id,
            "prompt_version": error.call.prompt_version,
            "attempts": error.call.attempts,
            "latency_ms": round((monotonic() - started) * 1000, 2),
            "usage": asdict(error.call.usage) if error.call.usage else None,
            "failure_reason": error.reason.value,
            "provider_failure_kind": error.provider_failure_kind.value
            if error.provider_failure_kind
            else None,
        }

    expected_fields = set(ExtractionResult.model_fields)
    present_fields = outcome.result.model_fields_set
    usage = outcome.call.usage
    shape_valid = present_fields == expected_fields
    return {
        "ok": shape_valid and usage is not None,
        "model": outcome.call.model_settings.model,
        "prompt_id": outcome.call.prompt_id,
        "prompt_version": outcome.call.prompt_version,
        "attempts": outcome.call.attempts,
        "latency_ms": round((monotonic() - started) * 1000, 2),
        "usage": asdict(usage) if usage else None,
        "shape": {
            "valid": shape_valid,
            "fields": sorted(present_fields),
            "reported_facts_count": len(outcome.result.reported_facts),
            "questions_count": len(outcome.clarification.questions),
        },
    }


def format_live_report(report: dict[str, Any]) -> str:
    return json.dumps(report, sort_keys=True)
