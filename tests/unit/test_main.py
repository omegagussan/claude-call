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
