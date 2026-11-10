import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert resp.json() == {"message": "Claude Call Service"}


@pytest.mark.asyncio
async def test_get_call_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/calls/nonexistent_id")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Call not found"


@pytest.mark.asyncio
async def test_docs_and_openapi_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Swagger UI docs endpoint
        resp_docs = await client.get("/docs")
        assert resp_docs.status_code == 200
        assert "swagger-ui" in resp_docs.text

        # Redoc alternative docs endpoint
        resp_redoc = await client.get("/redoc")
        assert resp_redoc.status_code == 200
        assert "redoc" in resp_redoc.text

        # OpenAPI schema JSON endpoint
        resp_openapi = await client.get("/openapi.json")
        assert resp_openapi.status_code == 200
        assert resp_openapi.json()["info"]["title"] == "Claude Call - Fröken Ur & Telnyx"


def test_openapi_documents_default_500_response_on_every_operation():
    schema = app.openapi()
    for path in schema["paths"].values():
        for operation in path.values():
            response = operation["responses"]["500"]
            assert response["description"] == "Internal server error"
            assert response["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}
    error_schema = schema["components"]["schemas"]["ErrorResponse"]
    assert error_schema["properties"]["detail"]["type"] == "string"
    assert error_schema["required"] == ["detail"]
    assert "201" in schema["paths"]["/calls/froken-ur"]["post"]["responses"]
    assert "422" in schema["paths"]["/calls/froken-ur"]["post"]["responses"]
