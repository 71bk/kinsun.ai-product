"""Unit tests for app.api.ready — readiness endpoint."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.ready import router
from app.db.session import get_db_engine


def _create_test_app(db_engine_mock: MagicMock) -> FastAPI:
    """Create a minimal FastAPI app with the ready router and mocked engine."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_engine] = lambda: db_engine_mock
    return app


class TestReadyEndpoint:
    @pytest.mark.asyncio
    async def test_returns_200_when_db_connected(self) -> None:
        """GET /ready returns 200 with expected body when DB is reachable."""
        mock_engine = MagicMock()
        mock_engine.check_connectivity = AsyncMock(return_value=True)
        app = _create_test_app(mock_engine)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/ready")

        assert response.status_code == 200
        assert response.json() == {"status": "ready", "database": "connected"}

    @pytest.mark.asyncio
    async def test_returns_503_when_db_unavailable(self) -> None:
        """GET /ready returns 503 when check_connectivity returns False."""
        mock_engine = MagicMock()
        mock_engine.check_connectivity = AsyncMock(return_value=False)
        app = _create_test_app(mock_engine)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/ready")

        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "database": "unavailable"}

    @pytest.mark.asyncio
    async def test_returns_503_when_db_check_raises(self) -> None:
        """GET /ready returns 503 when check_connectivity raises an exception."""
        mock_engine = MagicMock()
        mock_engine.check_connectivity = AsyncMock(
            side_effect=ConnectionRefusedError("DB unreachable")
        )
        app = _create_test_app(mock_engine)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/ready")

        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "database": "unavailable"}

    @pytest.mark.asyncio
    async def test_returns_503_when_db_check_times_out(self) -> None:
        """GET /ready returns 503 when check_connectivity exceeds 3s timeout."""
        mock_engine = MagicMock()

        async def slow_check() -> bool:
            await asyncio.sleep(10)
            return True

        mock_engine.check_connectivity = slow_check
        app = _create_test_app(mock_engine)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/ready")

        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "database": "unavailable"}

    @pytest.mark.asyncio
    async def test_non_get_returns_405(self) -> None:
        """Non-GET methods return 405 Method Not Allowed."""
        mock_engine = MagicMock()
        mock_engine.check_connectivity = AsyncMock(return_value=True)
        app = _create_test_app(mock_engine)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for method in ["post", "put", "patch", "delete"]:
                response = await getattr(client, method)("/ready")
                assert response.status_code == 405, f"{method.upper()} should return 405"

    @pytest.mark.asyncio
    async def test_no_auth_required(self) -> None:
        """GET /ready succeeds without any authentication headers."""
        mock_engine = MagicMock()
        mock_engine.check_connectivity = AsyncMock(return_value=True)
        app = _create_test_app(mock_engine)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # No auth headers whatsoever
            response = await client.get("/ready", headers={})

        assert response.status_code == 200
