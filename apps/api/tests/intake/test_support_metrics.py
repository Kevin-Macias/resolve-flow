from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from conftest import Environment
from httpx import ASGITransport, AsyncClient
from langchain_core.runnables import RunnableConfig
from test_support_reads import reader

from api.db.models import IssueReport
from api.extraction.provider import ModelSettings, ProviderUsage
from api.extraction.service import ExtractionCallRecord
from api.main import create_app
from api.support import metrics
from api.support.metrics import SupportMetrics, SupportMetricsReader, saved_metrics
from api.workflow.checkpoints import open_checkpointer, workflow_config


async def client_app(e: Environment, monkeypatch: pytest.MonkeyPatch):
    await reader(e, monkeypatch)
    app = create_app()
    app.state.support_metrics = SupportMetricsReader(
        e.sessions, e.url, e.runtime.checkpoint_schema
    )
    return app


@pytest.mark.anyio
async def test_saved_metrics_empty_restart_archived_and_read_only(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
):
    e = environment
    app = await client_app(e, monkeypatch)
    path = f"/support/issue-reports/{e.report_id}/execution-metrics"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        empty = await client.get(path)
        assert empty.status_code == 200
        assert empty.json()["run_id"] is None and empty.json()["metrics"] is None
        view, _ = await e.service().start(e.report_id)
        async with open_checkpointer(e.url, e.runtime.checkpoint_schema) as saver:
            before = [item async for item in saver.alist(workflow_config(view.run_id))]
        response = await client.get(path)
        assert response.status_code == 200, response.text
        parsed = SupportMetrics.model_validate_json(response.text)
        assert (
            parsed.metrics is not None and parsed.metrics.model == "offline-intake-v1"
        )
        assert parsed.metrics.usage is None and parsed.metrics.latency_ms is None
        assert parsed.metrics.estimated_cost is None and parsed.metrics.attempts == 1
        assert parsed.run_id == view.run_id and parsed.provider_mode == "offline"
        app.state.support_metrics = SupportMetricsReader(
            e.sessions, e.url, e.runtime.checkpoint_schema
        )
        assert (await client.get(path)).json() == response.json()
        async with e.sessions() as session:
            report = await session.get(IssueReport, e.report_id)
            assert report
            report.status = "deleted"
            await session.commit()
        assert (await client.get(path)).json() == response.json()
        assert (
            await client.get(f"/support/issue-reports/{uuid4()}/execution-metrics")
        ).status_code == 404
        assert (
            await client.get("/support/issue-reports/bad/execution-metrics")
        ).status_code == 422
        async with open_checkpointer(e.url, e.runtime.checkpoint_schema) as saver:
            after = [item async for item in saver.alist(workflow_config(view.run_id))]
        assert before == after and e.provider.calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("token", "status"), [(None, 401), ("invalid", 401), ("customer-a", 403)]
)
async def test_denied_before_checkpoint_read(
    environment: Environment,
    monkeypatch: pytest.MonkeyPatch,
    token: str | None,
    status: int,
):
    e = environment
    app = await client_app(e, monkeypatch)
    await e.service().start(e.report_id)

    def forbidden(*args: object, **kwargs: object):
        pytest.fail("Denied request read checkpoints")

    monkeypatch.setattr(metrics, "open_checkpointer", forbidden)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/support/issue-reports/{e.report_id}/execution-metrics",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
    assert response.status_code == status


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("change", "status"),
    [("revoke", 404), ("corrupt", 503), ("failure", 200), ("zero", 200)],
)
async def test_saved_validation_and_fresh_access(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, change: str, status: int
):
    e = environment
    app = await client_app(e, monkeypatch)
    await e.service().start(e.report_id)

    @asynccontextmanager
    async def changed(url: str, schema: str) -> AsyncGenerator[object]:
        async with open_checkpointer(url, schema) as saver:

            async def read(config: RunnableConfig):
                saved = await saver.aget_tuple(config)
                assert saved
                values = dict(saved.checkpoint["channel_values"])
                if change == "corrupt":
                    values["extraction_call"] = {"model": "private output"}
                elif change == "zero":
                    values["extraction_call"] = replace(
                        values["extraction_call"], usage=ProviderUsage(0, 0, 0)
                    )
                elif change == "failure":
                    values["extraction_call"] = replace(
                        values["extraction_call"], attempts=3, usage=None
                    )
                return SimpleNamespace(checkpoint={"channel_values": values})

            yield SimpleNamespace(aget_tuple=read)
        if change == "revoke":
            monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", "{}")

    monkeypatch.setattr(metrics, "open_checkpointer", changed)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        response = await client.get(
            f"/support/issue-reports/{e.report_id}/execution-metrics"
        )
    assert response.status_code == status, response.text
    assert "private output" not in response.text
    if change == "zero":
        assert response.json()["metrics"]["usage"]["total_tokens"] == 0
    if change == "failure":
        assert response.json()["metrics"]["attempts"] == 3
    assert e.provider.calls == 1


@pytest.mark.parametrize("bad", [True, -1, 1.5, "3"])
def test_invalid_usage(bad: object):
    call = ExtractionCallRecord(
        "prompt",
        "1",
        ModelSettings("model"),
        "Schema",
        attempts=1,
        usage=ProviderUsage(cast(int, bad), 0, 0),
    )
    with pytest.raises(ValueError):
        saved_metrics(call)


def test_projection_excludes_settings_and_missing_record_is_not_zero():
    call = ExtractionCallRecord(
        "prompt", "1", ModelSettings("model", temperature=0.5), "Schema", attempts=2
    )
    record = saved_metrics(call)
    assert record.usage is None and record.model_dump()["latency_ms"] is None
    assert "temperature" not in record.model_dump_json()
    with pytest.raises(ValueError):
        saved_metrics(replace(call, attempts=0))
    with pytest.raises(ValueError):
        saved_metrics(replace(call, model_settings=ModelSettings("")))


@pytest.mark.anyio
async def test_latest_round_replaces_previous_record(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
):
    from test_lifecycle import reply

    e = environment
    app = await client_app(e, monkeypatch)
    view, _ = await e.service().start(e.report_id)
    e.provider.settings = ModelSettings("second-extraction")
    await e.service().clarify(view.run_id, reply(view))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        response = await client.get(
            f"/support/issue-reports/{e.report_id}/execution-metrics"
        )
    assert response.status_code == 200
    assert response.json()["metrics"]["model"] == "second-extraction"
    assert response.json()["scope"] == "latest_intake_extraction"
    assert e.provider.calls == 2


@pytest.mark.anyio
async def test_handled_failure_preserves_returned_usage(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
):
    from api.extraction.provider import FakeProvider, ProviderResult

    e = environment
    e.runtime.provider = FakeProvider(
        ProviderResult(text="invalid json", usage=ProviderUsage(12, 2, 14))
    )
    app = await client_app(e, monkeypatch)
    view, _ = await e.service().start(e.report_id)
    assert view.status == "failed"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        response = await client.get(
            f"/support/issue-reports/{e.report_id}/execution-metrics"
        )
    assert response.status_code == 200
    assert response.json()["metrics"]["usage"]["total_tokens"] == 14
    assert "invalid json" not in response.text


@pytest.mark.anyio
async def test_accepted_run_without_record_is_empty_pending(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
):
    from test_recovery import BeforeDispatch, Crash

    e = environment
    app = await client_app(e, monkeypatch)
    with pytest.raises(Crash):
        await BeforeDispatch(e.runtime, "customer-a").start(e.report_id)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        response = await client.get(
            f"/support/issue-reports/{e.report_id}/execution-metrics"
        )
    assert response.status_code == 200
    assert response.json()["metrics"] is None and response.json()["operation_pending"]
    assert e.provider.calls == 0
