"""Durable per-attempt accounting with real PostgreSQL and no live providers."""

import asyncio
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import Environment
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.accounting.contracts import Pricing, Usage, estimate
from api.accounting.models import ModelCallAttempt
from api.accounting.reader import AccountingReader
from api.accounting.recording import AccountingUnavailable, Recorder, Scope, recording
from api.db.models import Base, IssueReport
from api.extraction.provider import (
    FakeProvider,
    ModelSettings,
    ProviderError,
    ProviderFailureKind,
    ProviderResult,
    ProviderUsage,
)
from api.extraction.service import ExtractionError, RetryPolicy, extract_issue_report
from api.main import create_app
from api.observability import bind

SECRET = "private-report-prompt-output-and-provider-error"


def card(version: str = "v1", rate: str = "1") -> dict[str, object]:
    return {
        "version": version,
        "rates": [
            {
                "model": "priced-model",
                "input_per_million": rate,
                "output_per_million": "2",
                "cached_input_per_million": "0.5",
            }
        ],
    }


@pytest.mark.parametrize(
    "case",
    ["known", "zero", "no_rate", "no_usage", "no_cache", "offline", "no_pricing"],
)
def test_explicit_price_and_unavailable_values(case: str) -> None:
    usage = Usage(
        input_tokens=100, output_tokens=20, total_tokens=120, cached_input_tokens=10
    )
    config = Pricing.model_validate(card())
    mode = "offline" if case == "offline" else "live"
    if case == "zero":
        usage = Usage(
            input_tokens=0, output_tokens=0, total_tokens=0, cached_input_tokens=0
        )
    if case == "no_cache":
        usage = usage.model_copy(update={"cached_input_tokens": None})
    value, reason = estimate(
        None if case == "no_pricing" else config,
        "other" if case == "no_rate" else "priced-model",
        None if case == "no_usage" else usage,
        mode,
    )
    if case in ("known", "zero"):
        assert value is not None and reason == "available"
        assert value.usd == (Decimal("0") if case == "zero" else Decimal("0.000135"))
    else:
        assert value is None and reason != "available"


async def support(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> tuple[AccountingReader, Scope]:
    e = environment
    run, _ = await e.service().start(e.report_id)
    async with e.sessions() as session:
        report = await session.get(IssueReport, e.report_id)
        assert report is not None
        monkeypatch.setenv(
            "DEMO_SUPPORT_ACCOUNT_IDS",
            json.dumps({e.tokens["support"]: [str(report.customer_account_id)]}),
        )
        # Reader checks evidence scopes too; this fixture otherwise needs intake only.
        connection = await session.connection()
        await connection.run_sync(
            lambda conn: Base.metadata.tables["evidence_analyses"].create(
                conn, checkfirst=True
            )
        )
        await session.commit()
        account = report.customer_account_id
    return AccountingReader(e.sessions), Scope(
        e.report_id, account, "intake", run.run_id, uuid4(), "live"
    )


@pytest.mark.anyio
async def test_invalid_application_output_retains_usage_and_frozen_rate(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    reader, scope = await support(e, monkeypatch)
    monkeypatch.setenv("MODEL_PRICING", json.dumps(card()))
    provider = FakeProvider(
        ProviderResult(
            text=SECRET,
            usage=ProviderUsage(100, 20, 120),
            cached_input_tokens=0,
            resolved_model="priced-model",
        ),
        ModelSettings("priced-model"),
    )
    with recording(e.sessions, scope), bind(request_id=uuid4()):
        with pytest.raises(ExtractionError):
            await extract_issue_report(SECRET, provider)
    monkeypatch.setenv("MODEL_PRICING", json.dumps(card("v2", "10")))
    restarted = AccountingReader(e.sessions)
    result = await restarted.get("support", e.report_id)
    priced = [item for item in result.attempts if item.provider_mode == "live"]
    assert len(priced) == 1 and priced[0].outcome == "response_received"
    assert priced[0].cost is not None and priced[0].cost.pricing_version == "v1"
    assert priced[0].cost.usd == Decimal("0.00014")
    assert result.totals.known_live_total_tokens == 120 and result.totals.cost_complete
    async with e.sessions() as session:
        stored = list(await session.scalars(select(ModelCallAttempt)))
        assert SECRET not in str([row.record for row in stored])
    assert (await reader.get("support", e.report_id)).totals == result.totals
    app = create_app()
    app.state.session_factory = e.sessions
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/support/issue-reports/{e.report_id}/model-accounting",
            headers={"Authorization": "Bearer support"},
        )
    assert response.status_code == 200, response.text
    priced_json = next(
        row for row in response.json()["attempts"] if row["provider_mode"] == "live"
    )
    assert priced_json["cost"]["usd"] == "0.00014" and "pricing" not in priced_json


@pytest.mark.anyio
async def test_failed_start_never_dispatches_and_failed_finish_leaves_durable_start(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    reader, scope = await support(e, monkeypatch)
    provider = FakeProvider(ProviderResult(text=SECRET), ModelSettings("priced-model"))
    bad = create_async_engine("postgresql+psycopg://postgres:test@127.0.0.1:1/missing")
    unavailable = async_sessionmaker(bad, expire_on_commit=False)
    recorder = Recorder(unavailable, scope)

    async def invoke() -> ProviderResult:
        return await provider.generate(SECRET, SECRET)

    with pytest.raises(AccountingUnavailable):
        await recorder.call(invoke, "extraction", "priced-model", "test", "1")
    assert provider.calls == []
    recorder = Recorder(e.sessions, scope)

    async def returned() -> ProviderResult:
        recorder.sessions = unavailable
        return await invoke()

    with pytest.raises(AccountingUnavailable):
        await recorder.call(returned, "extraction", "priced-model", "test", "1")
    assert len(provider.calls) == 1
    saved = await reader.get("support", e.report_id)
    pending = [row for row in saved.attempts if row.outcome == "started"]
    assert len(pending) == 1 and pending[0].usage is None and pending[0].cost is None
    assert saved.totals.missing_live_cost == 1 and not saved.totals.cost_complete
    await bad.dispose()


class RetryProvider(FakeProvider):
    async def generate(
        self,
        instructions: str,
        input_text: str,
        output_schema: type[BaseModel] | None = None,
    ) -> ProviderResult:
        self.calls.append((instructions, input_text, output_schema))
        if len(self.calls) == 1:
            raise ProviderError(SECRET, ProviderFailureKind.TRANSIENT)
        return self.result


@pytest.mark.anyio
async def test_retries_and_clarification_rounds_keep_separate_history(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    reader, scope = await support(e, monkeypatch)
    monkeypatch.setenv("MODEL_PRICING", json.dumps(card()))
    provider = RetryProvider(
        ProviderResult(
            refusal=SECRET, usage=ProviderUsage(10, 1, 11), cached_input_tokens=0
        ),
        ModelSettings("priced-model"),
    )
    with recording(e.sessions, scope):
        with pytest.raises(ExtractionError):
            await extract_issue_report(
                SECRET, provider, RetryPolicy(base_delay_seconds=0)
            )
    saved = await reader.get("support", e.report_id)
    live = [row for row in saved.attempts if row.provider_mode == "live"]
    assert [row.attempt for row in live] == [1, 2]
    assert live[0].call_id == live[1].call_id and live[0].id != live[1].id
    assert live[0].usage is None and live[1].usage is not None
    assert saved.totals.retries == 1 and saved.totals.missing_live_cost == 1
    run = await e.service().get(scope.scope_id)
    assert run.pending is not None
    from api.intake.schemas import ClarificationRequest

    await e.service().clarify(
        run.run_id,
        ClarificationRequest(
            operation_id=uuid4(),
            expected_revision=run.revision,
            pending_id=run.pending.pending_id,
            action="answer",
            answers=("Same account, no known cause.",),
        ),
    )
    later = await reader.get("support", e.report_id)
    assert len(later.attempts) > len(saved.attempts)
    assert {row.id for row in saved.attempts}.issubset(
        {row.id for row in later.attempts}
    )


@pytest.mark.anyio
async def test_api_access_read_only_and_legacy_coverage(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    reader, scope = await support(e, monkeypatch)
    app = create_app()
    app.state.session_factory = e.sessions
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = f"/support/issue-reports/{e.report_id}/model-accounting"
        before = e.provider.calls
        response = await client.get(path, headers={"Authorization": "Bearer support"})
        assert (
            response.status_code == 200
            and response.json()["totals"]["coverage_complete"]
        )
        assert (
            await client.get(path, headers={"Authorization": "Bearer customer-a"})
        ).status_code == 403
        assert (
            await client.get(path, headers={"Authorization": "Bearer unknown"})
        ).status_code == 401
        monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", "{}")
        assert (
            await client.get(path, headers={"Authorization": "Bearer support"})
        ).status_code == 404
        assert e.provider.calls == before
    async with e.sessions() as session:
        from api.intake.models import IntakeRun

        row = await session.get(IntakeRun, scope.scope_id)
        assert row is not None
        row.accounting_version = None
        await session.commit()
    monkeypatch.setenv(
        "DEMO_SUPPORT_ACCOUNT_IDS",
        json.dumps({e.tokens["support"]: [str(scope.account_id)]}),
    )
    assert not (await reader.get("support", e.report_id)).totals.coverage_complete


@pytest.mark.anyio
async def test_process_exit_keeps_started_attempt(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    reader, scope = await support(e, monkeypatch)
    script = """
import asyncio, os, sys
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from api.accounting.recording import Recorder, Scope
async def main():
 engine=create_async_engine(sys.argv[1].replace('postgresql://','postgresql+psycopg://'),connect_args={'options': '-csearch_path='+sys.argv[2]+',public'})
 scope=Scope(UUID(sys.argv[3]),UUID(sys.argv[4]),'intake',UUID(sys.argv[5]),UUID(sys.argv[6]),'live')
 async def invoke(): os._exit(73)
 await Recorder(async_sessionmaker(engine,expire_on_commit=False),scope).call(invoke,'extraction','priced-model','test','1')
asyncio.run(main())
"""
    result = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-c",
            script,
            e.url,
            e.schema,
            str(scope.report_id),
            str(scope.account_id),
            str(scope.scope_id),
            str(scope.operation_id),
        ],
        env={**os.environ, "PYTHONPATH": str(Path.cwd() / "src")},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 73, result.stderr
    rows = await reader.get("support", e.report_id)
    assert rows.totals.unfinished_attempts == 1 and rows.totals.missing_live_cost == 1


@pytest.mark.anyio
async def test_changed_rate_card_needs_new_version_before_dispatch(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    _, scope = await support(e, monkeypatch)
    monkeypatch.setenv("MODEL_PRICING", json.dumps(card()))
    first = Recorder(e.sessions, scope)
    provider = FakeProvider(
        ProviderResult(usage=ProviderUsage(0, 0, 0), cached_input_tokens=0),
        ModelSettings("priced-model"),
    )

    async def invoke() -> ProviderResult:
        return await provider.generate(SECRET, SECRET)

    await first.call(invoke, "extraction", "priced-model", "test", "1")
    monkeypatch.setenv("MODEL_PRICING", json.dumps(card("v1", "10")))
    with pytest.raises(AccountingUnavailable):
        await Recorder(e.sessions, scope).call(
            invoke, "extraction", "priced-model", "test", "1"
        )
    assert len(provider.calls) == 1
    monkeypatch.setenv("MODEL_PRICING", json.dumps(card("v2", "10")))
    await Recorder(e.sessions, scope).call(
        invoke, "extraction", "priced-model", "test", "1"
    )
    assert len(provider.calls) == 2


@pytest.mark.anyio
async def test_embedding_requests_retain_actual_usage_without_counting_batches_as_retries(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock

    from api.accounting.embedding import EmbeddingEndpoint

    e = environment
    reader, scope = await support(e, monkeypatch)
    monkeypatch.setenv(
        "MODEL_PRICING",
        json.dumps(
            {
                "version": "embedding-v1",
                "rates": [
                    {
                        "model": "text-embedding-3-small",
                        "input_per_million": "1",
                        "output_per_million": "0",
                    }
                ],
            }
        ),
    )
    endpoint = AsyncMock()
    endpoint.create.return_value = {
        "data": [{"embedding": [0.1]}],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 25, "total_tokens": 25},
    }
    adapter = EmbeddingEndpoint(endpoint)
    parent = uuid4()
    with recording(e.sessions, scope), bind(call_id=parent):
        await adapter.create(input=[SECRET], model="text-embedding-3-small")
        await adapter.create(input=[SECRET], model="text-embedding-3-small")
    result = await reader.get("support", e.report_id)
    rows = [row for row in result.attempts if row.component == "embedding"]
    assert len(rows) == 2 and rows[0].call_id != rows[1].call_id
    assert all(row.parent_call_id == parent and row.attempt == 1 for row in rows)
    assert result.totals.retries == 0 and result.totals.known_live_total_tokens == 50
    assert result.totals.known_live_cost_usd == Decimal("0.00005")
    assert all(row.cost is not None for row in rows)


@pytest.mark.anyio
async def test_incomplete_provider_result_retains_reported_usage(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = environment
    reader, scope = await support(e, monkeypatch)
    monkeypatch.setenv("MODEL_PRICING", json.dumps(card()))

    async def invoke() -> ProviderResult:
        raise ProviderError(
            SECRET,
            usage=ProviderUsage(5, 2, 7),
            resolved_model="priced-model",
            cached_input_tokens=0,
        )

    with pytest.raises(ProviderError):
        await Recorder(e.sessions, scope).call(
            invoke, "extraction", "priced-model", "test", "1"
        )
    result = await reader.get("support", e.report_id)
    row = next(row for row in result.attempts if row.provider_mode == "live")
    assert (
        row.outcome == "provider_error"
        and row.usage is not None
        and row.usage.total_tokens == 7
    )
    assert row.cost is not None and row.cost.usd == Decimal("0.000009")


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["timeout", "cancelled"])
async def test_provider_timeout_and_cancellation_have_distinct_durable_outcomes(
    environment: Environment, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    e = environment
    reader, scope = await support(e, monkeypatch)

    class Interrupted(FakeProvider):
        async def generate(
            self,
            instructions: str,
            input_text: str,
            output_schema: type[BaseModel] | None = None,
        ) -> ProviderResult:
            if kind == "cancelled":
                raise asyncio.CancelledError(SECRET)
            await asyncio.sleep(1)
            return self.result

    with recording(e.sessions, scope):
        with pytest.raises(
            asyncio.CancelledError if kind == "cancelled" else ExtractionError
        ):
            await extract_issue_report(
                SECRET,
                Interrupted(ProviderResult(), ModelSettings("priced-model")),
                RetryPolicy(max_attempts=1, timeout_seconds=0.001),
            )
    value = await reader.get("support", e.report_id)
    rows = [row for row in value.attempts if row.provider_mode == "live"]
    assert len(rows) == 1 and rows[0].outcome == kind
    assert rows[0].usage is None and rows[0].cost is None
