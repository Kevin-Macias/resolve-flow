"""Real PostgreSQL evidence lifecycle and the approved support access boundary."""

import asyncio
import json
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from conftest import Environment
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from api.db.models import Base, IssueReport, User
from api.knowledge.citations import CitationReport
from api.knowledge.markdown import MarkdownDocument
from api.knowledge.retrieval import RetrievalRequest, RetrievalResult
from api.main import create_app
from api.support.evidence import SupportEvidenceService
from api.support.evidence_models import EvidenceAnalysis
from api.support.evidence_runtime import EvidenceRuntime


@pytest.fixture
async def evidence(
    environment: Environment, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[tuple[Environment, SupportEvidenceService, AsyncClient], None]:
    e = environment
    async with e.sessions() as session:
        connection = await session.connection()
        await connection.run_sync(Base.metadata.tables["evidence_analyses"].create)
        report = await session.get(IssueReport, e.report_id)
        assert report is not None
        monkeypatch.setenv(
            "DEMO_SUPPORT_ACCOUNT_IDS",
            json.dumps({e.tokens["support"]: [str(report.customer_account_id)]}),
        )
        await session.commit()
    monkeypatch.setenv("EVIDENCE_PROVIDER_MODE", "offline")
    service = SupportEvidenceService(e.sessions, e.url)
    app = create_app()
    app.state.session_factory = e.sessions
    app.state.support_evidence = service
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer support"},
    ) as client:
        yield e, service, client


@pytest.mark.anyio
async def test_saved_restart_duplicate_archived_and_read_only(
    evidence: tuple[Environment, SupportEvidenceService, AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e, service, client = evidence
    path = f"/support/issue-reports/{e.report_id}"
    assert (await client.get(f"{path}/evidence-analysis")).json()["status"] == "absent"
    operation = uuid4()
    created = await client.post(
        f"{path}/evidence-analyses", json={"operation_id": str(operation)}
    )
    assert created.status_code == 200, created.text
    result = created.json()
    assert result["status"] == "ready" and result["simulated"]
    assert len(result["passages"]) == 5
    assert all(item["score_metric"] == "fixture" for item in result["passages"])
    assert all(
        item["citation"]["metadata"]["status"] == "current"
        for item in result["passages"]
    )
    assert (
        await client.post(
            f"{path}/evidence-analyses", json={"operation_id": str(operation)}
        )
    ).json() == result

    async def forbidden(*args: object) -> tuple[RetrievalResult, CitationReport]:
        raise AssertionError("GET or duplicate must never call a provider")

    monkeypatch.setattr(service.runtime, "generate", forbidden)
    assert (await client.get(f"{path}/evidence-analysis")).json() == result
    assert (
        await client.post(
            f"{path}/evidence-analyses", json={"operation_id": str(operation)}
        )
    ).json() == result
    restarted = SupportEvidenceService(e.sessions, e.url)
    assert (await restarted.get("support", e.report_id)).model_dump(
        mode="json"
    ) == result
    async with e.sessions() as session:
        report = await session.get(IssueReport, e.report_id)
        assert report is not None
        report.status = "deleted"
        await session.commit()
        assert (
            await session.scalar(select(func.count()).select_from(EvidenceAnalysis))
            == 1
        )
    assert (await restarted.get("support", e.report_id)).status == "ready"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "token, grants, expected",
    [
        ("customer-a", "valid", 403),
        ("unknown", "valid", 401),
        ("support", "{}", 404),
        ("support", '{"bad":"*"}', 503),
    ],
)
async def test_get_and_post_access_contract(
    evidence: tuple[Environment, SupportEvidenceService, AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
    token: str,
    grants: str,
    expected: int,
) -> None:
    e, _, client = evidence
    if grants != "valid":
        monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", grants)
    path = f"/support/issue-reports/{e.report_id}"
    headers = {"Authorization": f"Bearer {token}"}
    read = await client.get(f"{path}/evidence-analysis", headers=headers)
    write = await client.post(
        f"{path}/evidence-analyses",
        headers=headers,
        json={"operation_id": str(uuid4())},
    )
    assert read.status_code == write.status_code == expected
    assert "passages" not in read.text and "passages" not in write.text
    async with e.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(EvidenceAnalysis))
            == 0
        )


@pytest.mark.anyio
async def test_freshness_and_scoped_query(
    evidence: tuple[Environment, SupportEvidenceService, AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e, service, _ = evidence
    view, _ = await e.service().start(e.report_id)
    original = service.runtime.generate
    requests: list[RetrievalRequest] = []

    async def capture(
        request: RetrievalRequest, sources: tuple[MarkdownDocument, ...], mode: str
    ) -> tuple[RetrievalResult, CitationReport]:
        requests.append(request)
        return await original(request, sources, mode)

    monkeypatch.setattr(service.runtime, "generate", capture)
    saved = await service.create("support", e.report_id, uuid4())
    assert saved.input_revision == view.revision and not saved.older_input
    assert e.other_account not in requests[0].scope.customer_account_ids
    assert len(requests[0].scope.customer_account_ids) == 1
    async with e.sessions() as session:
        report = await session.get(IssueReport, e.report_id)
        assert report is not None
        report.description += " Additional reported observation."
        await session.commit()
    assert (await service.get("support", e.report_id)).older_input


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["provider", "empty", "cancel", "revoke", "input"])
async def test_failure_empty_uncertainty_and_rechecks(
    evidence: tuple[Environment, SupportEvidenceService, AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    e, service, client = evidence
    operation = uuid4()
    original = service.runtime.generate

    async def generate(
        request: RetrievalRequest, sources: tuple[MarkdownDocument, ...], mode: str
    ) -> tuple[RetrievalResult, CitationReport]:
        if failure == "provider":
            raise ValueError("private provider secret")
        if failure == "cancel":
            raise asyncio.CancelledError()
        if failure == "empty":
            return RetrievalResult(), CitationReport()
        result = await original(request, sources, mode)
        if failure == "revoke":
            monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", "{}")
        if failure == "input":
            async with e.sessions() as session:
                report = await session.get(IssueReport, e.report_id)
                assert report is not None
                report.description += " changed"
                await session.commit()
        return result

    monkeypatch.setattr(service.runtime, "generate", generate)
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await service.create("support", e.report_id, operation)
        assert (await service.get("support", e.report_id)).status == "pending"
        assert (
            await service.create("support", e.report_id, operation)
        ).status == "pending"
        with pytest.raises(HTTPException) as error:
            await service.create("support", e.report_id, uuid4())
        assert error.value.status_code == 409
    else:
        response = await client.post(
            f"/support/issue-reports/{e.report_id}/evidence-analyses",
            json={"operation_id": str(operation)},
        )
        assert "secret" not in response.text
        assert (
            response.status_code
            == {"provider": 503, "empty": 200, "revoke": 404, "input": 409}[failure]
        )
        if failure == "empty":
            assert (
                response.json()["status"] == "ready"
                and response.json()["passages"] == []
            )
        elif failure != "revoke":
            assert (await service.get("support", e.report_id)).status == "failed"


@pytest.mark.anyio
async def test_concurrency_and_intake_serialization(
    evidence: tuple[Environment, SupportEvidenceService, AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e, service, _ = evidence
    entered, release = asyncio.Event(), asyncio.Event()
    original = service.runtime.generate

    async def slow(
        request: RetrievalRequest, sources: tuple[MarkdownDocument, ...], mode: str
    ) -> tuple[RetrievalResult, CitationReport]:
        entered.set()
        await release.wait()
        return await original(request, sources, mode)

    monkeypatch.setattr(service.runtime, "generate", slow)
    task = asyncio.create_task(service.create("support", e.report_id, uuid4()))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        assert (await service.get("support", e.report_id)).status == "pending"
        with pytest.raises(HTTPException) as error:
            await SupportEvidenceService(e.sessions, e.url).create(
                "support", e.report_id, uuid4()
            )
        assert error.value.status_code == 409
        with pytest.raises(HTTPException) as error:
            await e.service().start(e.report_id)
        assert error.value.status_code == 409
    finally:
        release.set()
        await task


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    ["grants", "role", "ownership", "source_scope", "historical", "corruption"],
)
async def test_saved_reads_reauthorize_and_verify(
    evidence: tuple[Environment, SupportEvidenceService, AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    e, service, client = evidence
    saved = await service.create("support", e.report_id, uuid4())
    assert saved.analysis_id is not None
    if change == "grants":
        monkeypatch.setenv("DEMO_SUPPORT_ACCOUNT_IDS", "{}")
    elif change in ("role", "ownership", "corruption"):
        async with e.sessions() as session:
            if change == "role":
                user = await session.get(User, UUID(e.tokens["support"]))
                assert user is not None
                user.user_type = "customer"
                user.customer_account_id = e.other_account
            elif change == "ownership":
                report = await session.get(IssueReport, e.report_id)
                assert report is not None
                report.customer_account_id = e.other_account
            else:
                row = await session.get(EvidenceAnalysis, saved.analysis_id)
                assert row is not None and row.result_record is not None
                value = json.loads(json.dumps(row.result_record))
                value["result"]["evidence"][0]["text"] = "forged quote"
                row.result_record = value
            await session.commit()
    else:
        original_sources = await service.runtime.sources()
        target = saved.passages[0].citation.metadata.document_id

        async def changed_sources() -> tuple[MarkdownDocument, ...]:
            return tuple(
                source.model_copy(
                    update={
                        "metadata": source.metadata.model_copy(
                            update=(
                                {
                                    "access_class": "CUSTOMER_ACCOUNT",
                                    "customer_account_id": e.other_account,
                                }
                                if change == "source_scope"
                                else {"version": "later"}
                            )
                        )
                    }
                )
                if source.metadata.document_id == target
                else source
                for source in original_sources
            )

        monkeypatch.setattr(service.runtime, "sources", changed_sources)
    response = await client.get(
        f"/support/issue-reports/{e.report_id}/evidence-analysis"
    )
    assert (
        response.status_code
        == {
            "grants": 404,
            "role": 403,
            "ownership": 404,
            "source_scope": 404,
            "historical": 200,
            "corruption": 503,
        }[change]
    )
    if change == "historical":
        assert response.json()["passages"][0]["historical"]
    else:
        assert "excerpt" not in response.text


@pytest.mark.anyio
async def test_runtime_offline_sources_and_no_live_calls() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    runtime = EvidenceRuntime(async_sessionmaker())
    sources = await runtime.sources()
    assert len(sources) == 8
