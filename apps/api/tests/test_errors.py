from uuid import UUID

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from api.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_openapi_describes_the_shared_error_response() -> None:
    schema = create_app().openapi()
    responses = schema["paths"]["/issue-reports/"]["post"]["responses"]

    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert "ErrorResponse" in schema["components"]["schemas"]
    assert schema["paths"]["/ready"]["get"]["responses"]["503"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}


@pytest.mark.anyio
async def test_request_validation_has_stable_field_details() -> None:
    app = create_app()

    async def read_item(item_id: UUID) -> dict[str, str]:
        return {"id": str(item_id)}

    app.add_api_route("/_test/items/{item_id}", read_item, methods=["GET"])

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/_test/items/not-a-uuid")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed",
            "details": [{"location": ["path", "item_id"], "code": "uuid_parsing"}],
        }
    }
    assert "not-a-uuid" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "code", "message"),
    [
        (401, "unauthorized", "Identity required"),
        (403, "forbidden", "Not permitted"),
        (404, "not_found", "Issue report not found"),
        (409, "conflict", "Report changed"),
        (422, "validation_error", "Unknown service code"),
        (503, "service_unavailable", "Service unavailable"),
        (500, "internal_error", "Internal server error"),
    ],
)
async def test_http_errors_share_one_envelope(
    status: int, code: str, message: str
) -> None:
    app = create_app()

    async def fail() -> None:
        raise HTTPException(
            status_code=status, detail="Internal detail" if status >= 500 else message
        )

    app.add_api_route("/_test/fail", fail, methods=["GET"])

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/_test/fail")

    assert response.status_code == status
    assert response.json() == {
        "error": {"code": code, "message": message, "details": []}
    }


@pytest.mark.anyio
async def test_unexpected_error_hides_internal_detail() -> None:
    app = create_app()

    async def crash() -> None:
        raise RuntimeError("private database information")

    app.add_api_route("/_test/crash", crash, methods=["GET"])

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/_test/crash")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error",
            "details": [],
        }
    }
    assert "private database information" not in response.text


@pytest.mark.anyio
async def test_framework_404_uses_error_envelope() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/missing-route")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": []}
    }


@pytest.mark.anyio
async def test_http_error_preserves_headers_and_rejects_non_string_detail() -> None:
    app = create_app()

    async def fail() -> None:
        raise HTTPException(
            status_code=401,
            detail={"private": "value"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.add_api_route("/_test/fail", fail, methods=["GET"])

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/_test/fail")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {
        "error": {"code": "unauthorized", "message": "Unauthorized", "details": []}
    }
