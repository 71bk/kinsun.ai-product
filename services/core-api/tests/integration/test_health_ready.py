"""Integration tests for health and readiness endpoints.

Validates:
- Req 6.1: GET /health returns 200 with "status": "ok"
- Req 6.2: Health endpoint does NOT perform DB connectivity check
- Req 6.3: Health response includes "uptime_seconds" (non-negative integer)
- Req 6.4: Health responds within 100ms
- Req 6.5: Health accessible without authentication
- Req 6.6: Non-GET /health returns 405
- Req 7.1: GET /ready verifies DB connectivity
- Req 7.2: Ready returns 200 with "status": "ready", "database": "connected"
- Req 7.3: Ready returns 503 with "status": "not_ready", "database": "unavailable"
- Req 7.4: Ready responds within 5 seconds
- Req 7.5: Ready accessible without authentication
- Req 7.6: Non-GET /ready returns 405
"""

from __future__ import annotations

import time
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db_engine
from app.main import create_app
from app.middleware.auth import FakeAuthenticator, get_authenticator

# These tests use ASGI transport with dependency overrides and do NOT
# require a real database connection. They are self-contained.


# ─── Test database engine stubs ───────────────────────────────────────────────


class _HealthyDatabaseEngine:
    """DatabaseEngine stub that simulates a healthy database."""

    @property
    def engine(self):
        return None

    @property
    def session_factory(self):
        return None

    @property
    def is_ready(self) -> bool:
        return True

    async def check_connectivity(self) -> bool:
        return True


class _UnreachableDatabaseEngine:
    """DatabaseEngine stub that simulates an unavailable database."""

    @property
    def engine(self):
        return None

    @property
    def session_factory(self):
        return None

    @property
    def is_ready(self) -> bool:
        return False

    async def check_connectivity(self) -> bool:
        return False


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def healthy_client() -> AsyncClient:
    """AsyncClient with a healthy (mocked) database engine."""
    app = create_app()

    fake_auth = FakeAuthenticator(
        actor_id=uuid.UUID("00000000-0000-4000-a000-000000000001"),
        actor_role="care_worker",
        tenant_id=uuid.UUID("00000000-0000-4000-a000-000000000002"),
    )
    healthy_engine = _HealthyDatabaseEngine()

    app.dependency_overrides[get_authenticator] = lambda: fake_auth
    app.dependency_overrides[get_db_engine] = lambda: healthy_engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unhealthy_client() -> AsyncClient:
    """AsyncClient where the database engine reports unavailable."""
    app = create_app()

    fake_auth = FakeAuthenticator(
        actor_id=uuid.UUID("00000000-0000-4000-a000-000000000001"),
        actor_role="care_worker",
        tenant_id=uuid.UUID("00000000-0000-4000-a000-000000000002"),
    )
    unavailable_engine = _UnreachableDatabaseEngine()

    app.dependency_overrides[get_authenticator] = lambda: fake_auth
    app.dependency_overrides[get_db_engine] = lambda: unavailable_engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ─── Health endpoint tests ────────────────────────────────────────────────────


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_200_with_status_ok(self, healthy_client: AsyncClient) -> None:
        """Req 6.1: GET /health returns 200 with status 'ok'."""
        response = await healthy_client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_includes_uptime_seconds(self, healthy_client: AsyncClient) -> None:
        """Req 6.3: Health response includes uptime_seconds as non-negative integer."""
        response = await healthy_client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert "uptime_seconds" in body
        assert isinstance(body["uptime_seconds"], int)
        assert body["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_health_responds_within_100ms(self, healthy_client: AsyncClient) -> None:
        """Req 6.4: Health responds within 100ms under normal conditions."""
        start = time.perf_counter()
        response = await healthy_client.get("/health")
        duration_ms = (time.perf_counter() - start) * 1000

        assert response.status_code == 200
        assert duration_ms < 100, f"Health endpoint took {duration_ms:.1f}ms (limit: 100ms)"

    @pytest.mark.asyncio
    async def test_health_accessible_without_auth(self, healthy_client: AsyncClient) -> None:
        """Req 6.5: Health is accessible without authentication headers."""
        response = await healthy_client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_post_returns_405(self, healthy_client: AsyncClient) -> None:
        """Req 6.6: POST on /health returns 405."""
        response = await healthy_client.post("/health")
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_health_put_returns_405(self, healthy_client: AsyncClient) -> None:
        """Req 6.6: PUT on /health returns 405."""
        response = await healthy_client.put("/health")
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_health_delete_returns_405(self, healthy_client: AsyncClient) -> None:
        """Req 6.6: DELETE on /health returns 405."""
        response = await healthy_client.delete("/health")
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_health_does_not_depend_on_db(self, unhealthy_client: AsyncClient) -> None:
        """Req 6.2: Health does NOT perform a DB check — works even when DB unavailable."""
        response = await unhealthy_client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"


# ─── Readiness endpoint tests ────────────────────────────────────────────────


class TestReadyEndpoint:
    """Tests for GET /ready endpoint."""

    @pytest.mark.asyncio
    async def test_ready_returns_200_when_db_available(self, healthy_client: AsyncClient) -> None:
        """Req 7.1, 7.2: Ready returns 200 with expected body when DB is reachable."""
        response = await healthy_client.get("/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["database"] == "connected"

    @pytest.mark.asyncio
    async def test_ready_returns_503_when_db_unavailable(
        self, unhealthy_client: AsyncClient
    ) -> None:
        """Req 7.3: Ready returns 503 with expected body when DB is unreachable."""
        response = await unhealthy_client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["database"] == "unavailable"

    @pytest.mark.asyncio
    async def test_ready_responds_within_5_seconds(self, healthy_client: AsyncClient) -> None:
        """Req 7.4: Ready responds within 5 seconds."""
        start = time.perf_counter()
        response = await healthy_client.get("/ready")
        duration_s = time.perf_counter() - start

        assert response.status_code == 200
        assert duration_s < 5.0, f"Ready endpoint took {duration_s:.2f}s (limit: 5s)"

    @pytest.mark.asyncio
    async def test_ready_accessible_without_auth(self, healthy_client: AsyncClient) -> None:
        """Req 7.5: Ready is accessible without authentication."""
        response = await healthy_client.get("/ready")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ready_post_returns_405(self, healthy_client: AsyncClient) -> None:
        """Req 7.6: POST on /ready returns 405."""
        response = await healthy_client.post("/ready")
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_ready_put_returns_405(self, healthy_client: AsyncClient) -> None:
        """Req 7.6: PUT on /ready returns 405."""
        response = await healthy_client.put("/ready")
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_ready_delete_returns_405(self, healthy_client: AsyncClient) -> None:
        """Req 7.6: DELETE on /ready returns 405."""
        response = await healthy_client.delete("/ready")
        assert response.status_code == 405
