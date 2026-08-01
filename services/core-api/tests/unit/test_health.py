"""Unit tests for the health endpoint."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.health import router


@pytest.fixture
def app() -> FastAPI:
    """Create a minimal FastAPI app with only the health router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    """Async test client for the health app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_returns_200(client: AsyncClient) -> None:
    """GET /health returns 200 status code."""
    response = await client.get("/health")
    assert response.status_code == 200


async def test_health_response_has_status_ok(client: AsyncClient) -> None:
    """GET /health response includes status: ok."""
    response = await client.get("/health")
    data = response.json()
    assert data["status"] == "ok"


async def test_health_response_has_uptime_seconds(client: AsyncClient) -> None:
    """GET /health response includes uptime_seconds as an integer."""
    response = await client.get("/health")
    data = response.json()
    assert "uptime_seconds" in data
    assert isinstance(data["uptime_seconds"], int)


async def test_health_uptime_is_non_negative(client: AsyncClient) -> None:
    """uptime_seconds should be >= 0."""
    response = await client.get("/health")
    data = response.json()
    assert data["uptime_seconds"] >= 0


async def test_health_post_returns_405(client: AsyncClient) -> None:
    """POST /health returns 405 Method Not Allowed."""
    response = await client.post("/health")
    assert response.status_code == 405


async def test_health_put_returns_405(client: AsyncClient) -> None:
    """PUT /health returns 405 Method Not Allowed."""
    response = await client.put("/health")
    assert response.status_code == 405


async def test_health_delete_returns_405(client: AsyncClient) -> None:
    """DELETE /health returns 405 Method Not Allowed."""
    response = await client.delete("/health")
    assert response.status_code == 405


async def test_health_patch_returns_405(client: AsyncClient) -> None:
    """PATCH /health returns 405 Method Not Allowed."""
    response = await client.patch("/health")
    assert response.status_code == 405


async def test_health_no_db_dependency() -> None:
    """Health endpoint module does not import any DB modules."""
    import inspect

    import app.api.health as health_module

    source = inspect.getsource(health_module)
    # Should not import from app.db or sqlalchemy
    assert "from app.db" not in source
    assert "import sqlalchemy" not in source
    assert "from sqlalchemy" not in source
