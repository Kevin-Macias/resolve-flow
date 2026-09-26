"""The live command's report can be checked without using a live model."""

import json

import pytest

from api.extraction.live_check import SYNTHETIC_REPORT, inspect_extraction
from api.extraction.provider import FakeProvider, ProviderResult, ProviderUsage


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def valid_response() -> str:
    return json.dumps(
        {
            "summary": "Team cannot submit invoices",
            "service_code": "invoicing",
            "severity": "medium",
            "confidence": "high",
            "reported_facts": ["Customer reports invoice submission fails"],
            "missing_data": ["Start time"],
            "contradictions": [],
            "questions": ["When did this begin?"],
        }
    )


@pytest.mark.anyio
async def test_live_report_records_shape_latency_and_usage_without_report_text() -> (
    None
):
    provider = FakeProvider(
        ProviderResult(text=valid_response(), usage=ProviderUsage(18, 42, 60))
    )

    report = await inspect_extraction(provider)

    assert report["ok"] is True
    assert report["latency_ms"] >= 0
    assert report["usage"] == {
        "input_tokens": 18,
        "output_tokens": 42,
        "total_tokens": 60,
    }
    assert report["shape"]["valid"] is True
    assert report["shape"]["questions_count"] == 1
    assert SYNTHETIC_REPORT not in json.dumps(report)
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_live_report_records_failure_without_model_text() -> None:
    report = await inspect_extraction(FakeProvider(ProviderResult(refusal="No")))

    assert report["ok"] is False
    assert report["failure_reason"] == "refusal"
    assert report["usage"] is None
    assert "No" not in json.dumps(report)


@pytest.mark.anyio
async def test_live_report_fails_when_usage_is_unavailable() -> None:
    report = await inspect_extraction(
        FakeProvider(ProviderResult(text=valid_response()))
    )

    assert report["shape"]["valid"] is True
    assert report["usage"] is None
    assert report["ok"] is False
