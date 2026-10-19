"""Check emitted JSON and real application boundaries, not only LogRecord extras."""

import asyncio
import io
import json
import logging
import subprocess
import sys
from collections.abc import AsyncIterator, Generator
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, SecretStr, ValidationError
from starlette.responses import StreamingResponse
from starlette.types import Message, Receive, Scope, Send

from api.extraction.provider import (
    FakeProvider,
    ProviderError,
    ProviderFailureKind,
    ProviderResult,
)
from api.extraction.service import ExtractionError, RetryPolicy, extract_issue_report
from api.identity.context import RequestContext
from api.main import create_app
from api.observability import bind, context, emit, logger, trace
from api.observability.config import SafeJSONFormatter
from api.observability.middleware import RequestLoggingMiddleware
from api.workflow.actions import (
    ActionRisk,
    CreateTicketArguments,
    RiskLevel,
    propose_create_ticket,
)
from api.workflow.approval import ApprovalChoice, ApprovalReply, record_approval
from api.workflow.execution import (
    SimulatedCreateTicketTool,
    SimulatedTicketResult,
    ToolCallError,
    execute_approved_action,
)

SECRET = "private-token-password-report-source"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def output() -> Generator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SafeJSONFormatter())
    previous, level = logger.handlers[:], logger.level
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    try:
        yield stream
        assert SECRET not in stream.getvalue()
    finally:
        logger.handlers = previous
        logger.setLevel(level)


def events(output: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_closed_schema_rejects_payloads_and_invalid_values(output: io.StringIO) -> None:
    for fields in (
        {"password": SECRET},
        {"outcome": SECRET},
        {"attempt": True},
        {"run_id": SECRET},
        {"duration_ms": float("nan")},
    ):
        with pytest.raises(ValidationError):
            emit("api.error", **fields)
    assert output.getvalue() == ""


@pytest.mark.anyio
async def test_concurrent_http_requests_generate_ids_and_template_routes(
    output: io.StringIO,
) -> None:
    app = create_app()
    run_ids = [uuid4(), uuid4()]

    async def work(item: UUID) -> dict[str, bool]:
        with trace("run", component="intake", run_id=item):
            await asyncio.sleep(0)
        return {"ok": True}

    app.add_api_route("/work/{item}", work)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            *(
                client.get(
                    f"/work/{run}?token={SECRET}",
                    headers={
                        "Authorization": f"Bearer {SECRET}",
                        "X-Request-ID": str(run),
                    },
                )
                for run in run_ids
            )
        )
        missing = await client.get(f"/missing-{SECRET}?password={SECRET}")
    ids = [response.headers["X-Request-ID"] for response in responses]
    assert len(set(ids)) == 2 and all(UUID(value).version == 4 for value in ids)
    assert set(ids).isdisjoint(map(str, run_ids))
    for request_id, run_id in zip(ids, run_ids, strict=True):
        rows = [row for row in events(output) if row.get("request_id") == request_id]
        assert {row["run_id"] for row in rows if "run_id" in row} == {str(run_id)}
        finished = next(row for row in rows if row["event"] == "request.completed")
        assert finished["route"] == "/work/{item}" and finished["status_code"] == 200
    row = next(
        row
        for row in events(output)
        if row["event"] == "request.completed"
        and row["request_id"] == missing.headers["X-Request-ID"]
    )
    assert row["route"] == "<unmatched>" and row["outcome"] == "rejected"
    assert context.get().request_id is None


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 409, 422, 503, 500])
async def test_failures_keep_id_and_never_log_exception_text(
    output: io.StringIO, status: int
) -> None:
    app = create_app()

    async def fail() -> None:
        if status == 500:
            raise RuntimeError(SECRET)
        raise HTTPException(status, SECRET)

    app.add_api_route("/fail", fail)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/fail")
    assert response.status_code == status
    request_id = response.headers["X-Request-ID"]
    rows = events(output)
    assert all(row["request_id"] == request_id for row in rows)
    assert (
        next(row for row in rows if row["event"] == "request.completed")["status_code"]
        == status
    )
    assert context.get().request_id is None


@pytest.mark.anyio
async def test_stream_keeps_context_without_logging_snapshots(
    output: io.StringIO,
) -> None:
    app = create_app()

    async def streaming() -> StreamingResponse:
        async def chunks() -> AsyncIterator[str]:
            emit("run.started", component="intake")
            yield f"data: {SECRET}\n\n"
            await asyncio.sleep(0)
            emit("run.completed", component="intake", outcome="success")

        return StreamingResponse(chunks(), media_type="text/event-stream")

    app.add_api_route("/stream", streaming)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/stream")
    assert SECRET in response.text
    assert {row["request_id"] for row in events(output)} == {
        response.headers["X-Request-ID"]
    }
    assert events(output)[-1]["event"] == "request.completed"
    assert context.get().request_id is None


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["cancelled", "disconnected", "stream_error"])
async def test_stream_interruption_preserves_response_status_and_resets_context(
    output: io.StringIO, mode: str
) -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send(
            {"type": "http.response.body", "body": SECRET.encode(), "more_body": True}
        )
        if mode == "cancelled":
            raise asyncio.CancelledError(SECRET)
        if mode == "stream_error":
            raise RuntimeError(SECRET)
        await receive()

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "method": "GET", "path": f"/{SECRET}"}
    if mode == "disconnected":
        await RequestLoggingMiddleware(app)(scope, receive, send)
    else:
        with pytest.raises(
            asyncio.CancelledError if mode == "cancelled" else RuntimeError
        ):
            await RequestLoggingMiddleware(app)(scope, receive, send)
    row = events(output)[-1]
    assert row["status_code"] == 200
    assert row["outcome"] == ("error" if mode == "stream_error" else mode)
    assert context.get().request_id is None


class RetryingProvider(FakeProvider):
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
async def test_model_attempts_link_to_request_run_and_logical_call(
    output: io.StringIO,
) -> None:
    payload = {
        "summary": SECRET,
        "service_code": None,
        "severity": "low",
        "confidence": "low",
        "reported_facts": [SECRET],
        "missing_data": [],
        "contradictions": [],
        "questions": [],
    }
    provider = RetryingProvider(ProviderResult(text=json.dumps(payload)))
    request_id, run_id, operation_id = uuid4(), uuid4(), uuid4()
    with bind(request_id=request_id, run_id=run_id, operation_id=operation_id):
        await extract_issue_report(SECRET, provider, RetryPolicy(base_delay_seconds=0))
    rows = events(output)
    attempts = [row for row in rows if row["event"] == "provider.completed"]
    assert [row["attempt"] for row in attempts] == [1, 2]
    assert [row["outcome"] for row in attempts] == ["error", "success"]
    assert len({row["call_id"] for row in rows}) == 1
    assert all(
        row["request_id"] == str(request_id)
        and row["run_id"] == str(run_id)
        and row["operation_id"] == str(operation_id)
        for row in rows
    )
    assert rows[-1]["event"] == "model.completed" and rows[-1]["outcome"] == "success"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("result", "outcome", "code"),
    [
        (ProviderResult(refusal=SECRET), "rejected", "refusal"),
        (ProviderResult(text=SECRET), "error", "invalid_output"),
    ],
)
async def test_model_output_failure_has_safe_reason(
    output: io.StringIO, result: ProviderResult, outcome: str, code: str
) -> None:
    with pytest.raises(ExtractionError):
        await extract_issue_report(SECRET, FakeProvider(result))
    row = events(output)[-1]
    assert row["outcome"] == outcome and row["failure_code"] == code


class BrokenTool(SimulatedCreateTicketTool):
    async def create_ticket(
        self, arguments: CreateTicketArguments, idempotency_key: UUID
    ) -> SimulatedTicketResult:
        raise RuntimeError(SECRET)


@pytest.mark.anyio
async def test_tool_unknown_outcome_is_distinct_from_success(
    output: io.StringIO,
) -> None:
    proposal = propose_create_ticket(
        CreateTicketArguments(
            issue_report_id=uuid4(),
            title=SECRET,
            description=SECRET,
            service_code=None,
            severity=None,
        ),
        explanation=SECRET,
        expected_effect=SECRET,
        risk=ActionRisk(level=RiskLevel.LOW, reason=SECRET),
    )
    actor = RequestContext(uuid4(), "support", None)
    approval = record_approval(
        ApprovalReply(
            action_id=proposal.action_id,
            version=proposal.version,
            fingerprint=proposal.fingerprint(),
            decision=ApprovalChoice.APPROVE,
        ),
        proposal,
        actor,
    )
    with bind(request_id=uuid4(), run_id=uuid4()):
        with pytest.raises(ToolCallError):
            await execute_approved_action(proposal, approval, actor, BrokenTool())
        await execute_approved_action(
            proposal, approval, actor, SimulatedCreateTicketTool()
        )
    rows = [row for row in events(output) if row["event"] == "tool.completed"]
    assert [row["outcome"] for row in rows] == ["unknown", "success"]
    assert all(row["execution_id"] == str(proposal.idempotency_key) for row in rows)


def test_importing_app_does_not_configure_stdout() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            'from api.main import create_app; from api.observability import emit; create_app(); emit("request.started"); print("artifact")',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "artifact\n" and result.stderr == ""


def test_configured_server_and_sdk_output_is_sanitized_and_repeatable() -> None:
    script = """
import logging
from api.observability import emit
from api.observability.config import configure_logging
configure_logging()
configure_logging()
emit('request.started')
for name in ('uvicorn.error', 'httpx', 'httpcore', 'openai._base_client', 'sqlalchemy.engine', 'psycopg', 'langgraph'):
    try:
        raise RuntimeError('private-token-password-report-source')
    except RuntimeError:
        logging.getLogger(name).error('private-token-password-report-source %s', {'password': 'private-token-password-report-source'}, exc_info=True)
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert SECRET not in result.stdout + result.stderr and result.stderr == ""
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows) == 8 and rows[0]["event"] == "request.started"
    assert all(row["event"] == "runtime.error" for row in rows[1:])


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["timeout", "cancelled", "provider_timeout"])
async def test_model_interruption_and_provider_timeout_are_distinct(
    output: io.StringIO, mode: str
) -> None:
    class Interrupted(FakeProvider):
        async def generate(
            self,
            instructions: str,
            input_text: str,
            output_schema: type[BaseModel] | None = None,
        ) -> ProviderResult:
            if mode == "provider_timeout":
                raise ProviderError(SECRET, ProviderFailureKind.TIMEOUT)
            if mode == "cancelled":
                raise asyncio.CancelledError(SECRET)
            await asyncio.sleep(1)
            return self.result

    with pytest.raises(
        asyncio.CancelledError if mode == "cancelled" else ExtractionError
    ):
        await extract_issue_report(
            SECRET,
            Interrupted(ProviderResult()),
            RetryPolicy(max_attempts=1, timeout_seconds=0.001),
        )
    row = events(output)[-1]
    assert row["outcome"] == ("cancelled" if mode == "cancelled" else "timeout")
    assert context.get().call_id is None


def test_real_server_returns_correlation_header_without_raw_access_or_traceback() -> (
    None
):
    import socket
    import time
    from pathlib import Path
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("server_worker.py")),
                str(listener.fileno()),
            ],
            pass_fds=(listener.fileno(),),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urlopen(
                        f"http://127.0.0.1:{port}/health", timeout=0.5
                    ) as response:
                        assert response.status == 200
                    break
                except (URLError, TimeoutError):
                    assert process.poll() is None and time.monotonic() < deadline
                    time.sleep(0.05)
            request = Request(
                f"http://127.0.0.1:{port}/failure/{SECRET}?token={SECRET}",
                data=SECRET.encode(),
                headers={"Authorization": f"Bearer {SECRET}", "X-Request-ID": SECRET},
                method="POST",
            )
            with pytest.raises(HTTPError) as raised:
                urlopen(request, timeout=3)
            assert raised.value.code == 500
            request_id = raised.value.headers["X-Request-ID"]
            assert UUID(request_id).version == 4
            raised.value.close()
        finally:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
        assert process.returncode in (0, -15) and stderr == ""
        assert SECRET not in stdout + stderr
        rows = [json.loads(line) for line in stdout.splitlines()]
        requests = [row for row in rows if row.get("request_id") == request_id]
        assert any(row["event"] == "api.error" for row in requests)
        assert any(
            row["event"] == "request.completed"
            and row["route"] == "/failure/{item}"
            and row["status_code"] == 500
            for row in requests
        )


@pytest.mark.anyio
@pytest.mark.parametrize("documents", [False, True])
async def test_embedding_timeout_logs_safe_outcome(
    output: io.StringIO, documents: bool
) -> None:
    from unittest.mock import AsyncMock

    from httpx2 import Request as ProviderRequest
    from langchain_openai import OpenAIEmbeddings
    from openai import APITimeoutError

    from api.knowledge.embeddings import EmbeddingError, EmbeddingFailure
    from api.knowledge.langchain_embeddings import LangChainEmbeddingProvider

    client = AsyncMock()
    client.create.side_effect = APITimeoutError(
        request=ProviderRequest("POST", f"https://test/{SECRET}")
    )
    adapter = LangChainEmbeddingProvider(
        OpenAIEmbeddings(
            model="text-embedding-3-small",
            dimensions=1536,
            check_embedding_ctx_length=False,
            async_client=client,
            api_key=SecretStr(SECRET),
            max_retries=0,
        )
    )
    with pytest.raises(EmbeddingError) as error:
        if documents:
            await adapter.embed_documents((SECRET,))
        else:
            await adapter.embed_query(SECRET)
    assert error.value.reason == EmbeddingFailure.TIMEOUT
    row = events(output)[-1]
    assert row["component"] == "embedding" and row["outcome"] == "timeout"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("result", "outcome"),
    [(ProviderResult(refusal=SECRET), "rejected"), (ProviderResult(), "error")],
)
async def test_analysis_refusal_and_empty_output_are_visible_without_content(
    output: io.StringIO, result: ProviderResult, outcome: str
) -> None:
    from api.knowledge.evidence_analysis import EvidenceAnalysisInput
    from api.support.evidence_runtime import LiveAnalysisProvider

    with pytest.raises(ValueError):
        await LiveAnalysisProvider(FakeProvider(result)).analyze(
            EvidenceAnalysisInput(SECRET)
        )
    row = events(output)[-1]
    assert row["component"] == "analysis" and row["outcome"] == outcome
