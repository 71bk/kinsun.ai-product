"""Unit tests for the Request Logger middleware.

Tests cover:
- Correlation ID generation when header missing
- Correlation ID passthrough when header present
- Correlation ID attached to response headers
- Sensitive headers not logged
- Duration measurement
- tenant_id/actor_id inclusion on error responses
- Log emission failure does not interrupt request processing
"""

from __future__ import annotations

import logging
import uuid
from unittest.mock import patch

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware.logging import (
    SENSITIVE_HEADERS,
    RequestLoggerMiddleware,
    correlation_id_var,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _create_app(handler=None, status_code: int = 200) -> Starlette:
    """Create a minimal Starlette app with the middleware applied."""

    async def default_handler(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok", status_code=status_code)

    if handler is None:
        handler = default_handler

    app = Starlette(
        routes=[Route("/test", handler, methods=["GET", "POST"])],
    )
    app.add_middleware(RequestLoggerMiddleware)
    return app


# ─── Correlation ID tests ────────────────────────────────────────────────────


def test_correlation_id_generated_when_header_missing():
    """When no x-correlation-id header is sent, a UUID v4 is generated."""
    app = _create_app()
    client = TestClient(app)

    response = client.get("/test")

    assert response.status_code == 200
    cid = response.headers.get("x-correlation-id")
    assert cid is not None
    # Validate it's a proper UUID v4
    parsed = uuid.UUID(cid, version=4)
    assert str(parsed) == cid


def test_correlation_id_passthrough_when_header_present():
    """When x-correlation-id header is sent, it is preserved."""
    app = _create_app()
    client = TestClient(app)
    custom_id = str(uuid.uuid4())

    response = client.get("/test", headers={"x-correlation-id": custom_id})

    assert response.status_code == 200
    assert response.headers["x-correlation-id"] == custom_id


def test_correlation_id_set_in_contextvar():
    """The correlation_id ContextVar is populated during the request."""
    captured_cid = None

    async def handler(request: Request) -> PlainTextResponse:
        nonlocal captured_cid
        captured_cid = correlation_id_var.get()
        return PlainTextResponse("ok")

    app = _create_app(handler=handler)
    client = TestClient(app)
    custom_id = "test-correlation-123"

    client.get("/test", headers={"x-correlation-id": custom_id})

    assert captured_cid == custom_id


def test_correlation_id_generated_when_header_empty():
    """When x-correlation-id header is empty string, a new UUID is generated."""
    app = _create_app()
    client = TestClient(app)

    response = client.get("/test", headers={"x-correlation-id": ""})

    cid = response.headers.get("x-correlation-id")
    assert cid is not None
    # Should be a valid UUID (not empty)
    uuid.UUID(cid, version=4)


# ─── Sensitive header exclusion tests ────────────────────────────────────────


def test_sensitive_headers_not_logged(caplog):
    """Sensitive headers (authorization, cookie, x-api-key) must never appear in logs."""
    app = _create_app()
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get(
            "/test",
            headers={
                "authorization": "Bearer super-secret-token",
                "cookie": "session=private-cookie-value",
                "x-api-key": "secret-api-key-12345",
            },
        )

    # Verify sensitive values are NOT in any log record
    for record in caplog.records:
        log_text = str(record.__dict__)
        assert "super-secret-token" not in log_text
        assert "private-cookie-value" not in log_text
        assert "secret-api-key-12345" not in log_text


def test_sensitive_headers_frozenset_contents():
    """Verify the SENSITIVE_HEADERS set contains the expected entries."""
    assert "authorization" in SENSITIVE_HEADERS
    assert "cookie" in SENSITIVE_HEADERS
    assert "x-api-key" in SENSITIVE_HEADERS


# ─── Duration measurement tests ─────────────────────────────────────────────


def test_duration_ms_is_logged(caplog):
    """The log entry includes a non-negative duration_ms value."""
    app = _create_app()
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/test")

    assert len(caplog.records) >= 1
    record = caplog.records[-1]
    assert hasattr(record, "duration_ms")
    assert record.duration_ms >= 0


def test_log_entry_contains_required_fields(caplog):
    """The structured log entry includes all required fields."""
    app = _create_app()
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/test", headers={"x-correlation-id": "abc-123"})

    assert len(caplog.records) >= 1
    record = caplog.records[-1]
    # Check all required fields exist in extra
    assert record.method == "GET"
    assert record.path == "/test"
    assert record.status_code == 200
    assert record.correlation_id == "abc-123"
    assert hasattr(record, "timestamp")
    assert hasattr(record, "duration_ms")


# ─── Error response context tests ───────────────────────────────────────────


def test_tenant_id_and_actor_id_included_on_4xx(caplog):
    """On 4xx responses, tenant_id and actor_id are included if available."""
    test_tenant = str(uuid.uuid4())
    test_actor = str(uuid.uuid4())

    async def error_handler(request: Request) -> PlainTextResponse:
        # Simulate auth middleware setting request state (shared across middleware boundary)
        request.state.tenant_id = test_tenant
        request.state.actor_id = test_actor
        return PlainTextResponse("not found", status_code=404)

    app = _create_app(handler=error_handler)
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/test")

    assert len(caplog.records) >= 1
    record = caplog.records[-1]
    assert record.tenant_id == test_tenant
    assert record.actor_id == test_actor


def test_tenant_id_and_actor_id_included_on_5xx(caplog):
    """On 5xx responses, tenant_id and actor_id are included if available."""
    test_tenant = str(uuid.uuid4())
    test_actor = str(uuid.uuid4())

    async def error_handler(request: Request) -> PlainTextResponse:
        request.state.tenant_id = test_tenant
        request.state.actor_id = test_actor
        return PlainTextResponse("error", status_code=500)

    app = _create_app(handler=error_handler)
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/test")

    record = caplog.records[-1]
    assert record.tenant_id == test_tenant
    assert record.actor_id == test_actor


def test_tenant_id_actor_id_not_included_on_success(caplog):
    """On 2xx responses, tenant_id and actor_id are NOT in the log entry."""
    app = _create_app()
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/test")

    record = caplog.records[-1]
    assert not hasattr(record, "tenant_id")
    assert not hasattr(record, "actor_id")


def test_missing_actor_context_on_error_does_not_crash(caplog):
    """On 4xx/5xx with no actor context set, log entry omits tenant/actor gracefully."""

    async def error_handler(request: Request) -> PlainTextResponse:
        # Do NOT set _tenant_id_var or _actor_id_var
        return PlainTextResponse("bad request", status_code=400)

    app = _create_app(handler=error_handler)
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/test")

    assert response.status_code == 400
    record = caplog.records[-1]
    assert record.status_code == 400
    # tenant_id and actor_id should not be present (empty defaults)
    assert not hasattr(record, "tenant_id") or record.tenant_id == ""


# ─── Log emission failure tests ──────────────────────────────────────────────


def test_log_emission_failure_does_not_interrupt_request():
    """If logging raises an exception, the request still completes normally."""
    app = _create_app()
    client = TestClient(app)

    with patch("app.middleware.logging.logger.info", side_effect=RuntimeError("log crash")):
        response = client.get("/test")

    # Request should still complete successfully
    assert response.status_code == 200
    # Correlation ID should still be attached to response
    assert response.headers.get("x-correlation-id") is not None


# ─── Request/response body not logged tests ──────────────────────────────────


def test_request_body_not_logged(caplog):
    """Request body content must never appear in logs."""

    async def post_handler(request: Request) -> PlainTextResponse:
        # Read the body so it's available (simulating real handler)
        await request.body()
        return PlainTextResponse("created", status_code=201)

    app = Starlette(
        routes=[Route("/test", post_handler, methods=["POST"])],
    )
    app.add_middleware(RequestLoggerMiddleware)
    client = TestClient(app)

    secret_body = "super-secret-patient-data-12345"

    with caplog.at_level(logging.INFO, logger="app.request"):
        client.post("/test", content=secret_body)

    for record in caplog.records:
        log_text = str(record.__dict__)
        assert secret_body not in log_text
