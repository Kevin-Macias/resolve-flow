from uuid import UUID

import pytest
from conftest import Environment
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from test_lifecycle import reply

from api.extraction.provider import FakeProvider, ProviderResult
from api.extraction.schemas import Confidence, ExtractionResult
from api.main import create_app
from api.streaming.transport import customer_stream


@pytest.mark.anyio
async def test_two_round_limit_and_explicit_incomplete_continuation(
    environment: Environment,
) -> None:
    e = environment
    result = ExtractionResult(
        summary="Fixture",
        service_code=None,
        severity=None,
        confidence=Confidence.LOW,
        reported_facts=[],
        missing_data=["Unknown impact"],
        contradictions=[],
        questions=["What is affected?"],
    )
    provider = FakeProvider(ProviderResult(text=result.model_dump_json()))
    e.runtime.provider = provider
    view, _ = await e.service().start(e.report_id)
    for number in (1, 2):
        view = await e.service().clarify(view.run_id, reply(view))
        assert len(view.turns) == number
    assert (
        view.pending is not None
        and view.pending.mode == "continue_only"
        and not view.pending.questions
    )
    assert len(provider.calls) == 3
    final = await e.service().clarify(
        view.run_id, reply(view, action="continue_incomplete")
    )
    assert final.incomplete and len(provider.calls) == 3


@pytest.mark.anyio
async def test_extraction_failure_is_terminal_and_not_recoverable(
    environment: Environment,
) -> None:
    e = environment
    e.runtime.provider = FakeProvider(ProviderResult(refusal="PRIVATE refusal"))
    view, _ = await e.service().start(e.report_id)
    assert view.status == "failed" and not view.operation_pending
    assert "PRIVATE" not in view.model_dump_json()
    with pytest.raises(HTTPException) as caught:
        await e.service().recover(view.run_id, view.revision)
    assert caught.value.status_code == 409
    repeated, created = await e.service().start(e.report_id)
    assert repeated == view and not created


@pytest.mark.anyio
async def test_oversized_question_projection_fails_closed(
    environment: Environment,
) -> None:
    e = environment
    result = ExtractionResult(
        summary="Fixture",
        service_code=None,
        severity=None,
        confidence=Confidence.LOW,
        reported_facts=[],
        missing_data=["Unknown"],
        contradictions=[],
        questions=["x" * 2001],
    )
    e.runtime.provider = FakeProvider(ProviderResult(text=result.model_dump_json()))
    view, _ = await e.service().start(e.report_id)
    assert (
        view.status == "failed" and view.pending is None and not view.operation_pending
    )
    assert "x" * 2001 not in view.model_dump_json()


@pytest.mark.anyio
async def test_revocation_between_snapshot_and_terminal_event(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    view, _ = await e.service().start(e.report_id)
    response = await customer_stream(e.service(), view.run_id)
    frames = aiter(response.body_iterator)
    first = await anext(frames)
    assert "event: snapshot" in (
        first.decode() if isinstance(first, bytes) else str(first)
    )
    monkeypatch.setenv("DEMO_TOKEN_USER_IDS", "{}")
    last = await anext(frames)
    assert "access_lost" in (last.decode() if isinstance(last, bytes) else str(last))
    with pytest.raises(StopAsyncIteration):
        await anext(frames)
    assert e.provider.calls == 1


@pytest.mark.anyio
async def test_missing_checkpoints_sanitized_without_in_memory_fallback(
    environment: Environment,
) -> None:
    e = environment
    e.runtime.checkpoint_schema = "missing_intake_checkpoint_schema"
    with pytest.raises(HTTPException) as caught:
        await e.service().start(e.report_id)
    assert caught.value.status_code == 503 and e.provider.calls == 0
    pending = await e.service().for_report(e.report_id)
    assert pending.operation_pending and pending.snapshot.progress == "stage_failed"
    e.runtime.checkpoint_schema = f"{e.schema}_cp"
    recovered = await e.service().recover(pending.run_id, pending.revision)
    assert recovered.status == "needs_clarification" and e.provider.calls == 1


@pytest.mark.anyio
async def test_http_missing_identity_and_unconfigured_runtime() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        missing = await client.get(f"/intake-runs/{UUID(int=0)}")
        assert missing.status_code == 401
        unavailable = await client.get(
            f"/intake-runs/{UUID(int=0)}", headers={"Authorization": "Bearer fixture"}
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "service_unavailable"
