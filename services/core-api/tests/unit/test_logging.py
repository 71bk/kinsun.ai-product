"""Unit tests for the Request Logger middleware.

Tests cover:
- Correlation ID generation when header missing
- Correlation ID passthrough when header present
- Correlation ID attached to response headers
- Sensitive headers not logged
- Duration measurement
- tenant_id/actor_id inclusion on error responses
- Audit context binding from the authentication dependency, and its release
- Log emission failure does not interrupt request processing
"""

from __future__ import annotations

import logging
import uuid
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.api.error_handlers import register_exception_handlers
from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.middleware.auth import FakeAuthenticator, get_actor_context, get_authenticator
from app.middleware.logging import (
    SENSITIVE_HEADERS,
    RequestLoggerMiddleware,
    _actor_id_var,
    _tenant_id_var,
    bind_request_actor_context,
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


def _http_scope(path: str = "/test") -> dict:
    """Build the minimal ASGI scope a Starlette Request needs."""
    return {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "server": ("testserver", 80),
        "root_path": "",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
    }


def _last_request_record(caplog) -> logging.LogRecord:
    """Return the request logger's own entry, ignoring handler-emitted ones."""
    records = [record for record in caplog.records if record.name == "app.request"]
    assert records, "the request logger emitted no entry"
    return records[-1]


@pytest.fixture(autouse=True)
def _isolated_audit_context():
    """Keep one test's audit ContextVars from reaching the next test.

    Tests share a single context, so a binding left behind here would look
    exactly like the cross-request attribution bug the middleware guards against.
    """
    actor_token = _actor_id_var.set("")
    tenant_token = _tenant_id_var.set("")
    yield
    _actor_id_var.reset(actor_token)
    _tenant_id_var.reset(tenant_token)


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
    custom_id = "11111111-1111-4111-8111-111111111111"

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


@pytest.mark.parametrize(
    "invalid_id",
    [
        "abc-123",
        "11111111-1111-1111-8111-111111111111",
        "A" * 200,
    ],
)
def test_invalid_correlation_id_is_replaced(invalid_id: str) -> None:
    app = _create_app()
    client = TestClient(app)

    response = client.get("/test", headers={"x-correlation-id": invalid_id})

    generated = response.headers["x-correlation-id"]
    assert generated != invalid_id
    assert uuid.UUID(generated).version == 4


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

    correlation_id = "22222222-2222-4222-8222-222222222222"
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/test", headers={"x-correlation-id": correlation_id})

    assert len(caplog.records) >= 1
    record = caplog.records[-1]
    # Check all required fields exist in extra
    assert record.method == "GET"
    assert record.path == "/test"
    assert record.status_code == 200
    assert record.correlation_id == correlation_id
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


# ─── Audit context binding tests (M-06) ──────────────────────────────────────


def test_bind_request_actor_context_normalizes_identifiers() -> None:
    """UUIDs are stored as strings so the log entry is JSON-serialisable."""
    request = Request(_http_scope())
    actor_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    bind_request_actor_context(request, actor_id=actor_id, tenant_id=tenant_id)

    assert request.state.actor_id == str(actor_id)
    assert request.state.tenant_id == str(tenant_id)
    assert _actor_id_var.get() == str(actor_id)
    assert _tenant_id_var.get() == str(tenant_id)


def test_authenticated_error_response_is_attributed_to_the_actor(caplog):
    """An authenticated request that fails must not log an anonymous entry.

    This is the M-06 acceptance path end to end: the real authentication
    dependency binds the audit context, the route then raises a domain error,
    and the resulting 404 entry still carries actor, tenant and correlation ID.
    """
    actor_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    app = FastAPI()
    app.add_middleware(RequestLoggerMiddleware)
    register_exception_handlers(app)

    @app.get("/protected")
    async def protected(actor: ActorContext = Depends(get_actor_context)) -> dict:
        raise NotFoundError("Resource not found")

    app.dependency_overrides[get_authenticator] = lambda: FakeAuthenticator(
        actor_id=actor_id,
        tenant_id=tenant_id,
    )
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="app.request"):
        correlation_id = "33333333-3333-4333-8333-333333333333"
        response = client.get("/protected", headers={"x-correlation-id": correlation_id})

    assert response.status_code == 404
    record = _last_request_record(caplog)
    assert record.status_code == 404
    assert record.actor_id == str(actor_id)
    assert record.tenant_id == str(tenant_id)
    assert record.correlation_id == correlation_id


def test_unauthenticated_error_response_stays_anonymous(caplog):
    """A rejected credential has no trusted identity, so none is recorded."""
    app = FastAPI()
    app.add_middleware(RequestLoggerMiddleware)
    register_exception_handlers(app)

    @app.get("/protected")
    async def protected(actor: ActorContext = Depends(get_actor_context)) -> dict:
        return {"ok": True}

    class _RejectingAuthenticator:
        async def authenticate(self, request):
            raise RuntimeError("expired credential")

    app.dependency_overrides[get_authenticator] = _RejectingAuthenticator
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/protected")

    assert response.status_code == 401
    record = _last_request_record(caplog)
    assert not hasattr(record, "actor_id")
    assert not hasattr(record, "tenant_id")


@pytest.mark.asyncio
async def test_dispatch_releases_audit_context_after_the_request():
    """One request's actor must not survive into whatever runs next."""
    middleware = RequestLoggerMiddleware(app=None)
    outer_token = _actor_id_var.set("actor-from-an-earlier-caller")

    async def call_next(request: Request) -> PlainTextResponse:
        bind_request_actor_context(request, actor_id="actor-1", tenant_id="tenant-1")
        return PlainTextResponse("denied", status_code=403)

    try:
        response = await middleware.dispatch(Request(_http_scope()), call_next)

        assert response.status_code == 403
        assert _actor_id_var.get() == "actor-from-an-earlier-caller"
        assert _tenant_id_var.get() == ""
    finally:
        _actor_id_var.reset(outer_token)


@pytest.mark.asyncio
async def test_dispatch_releases_audit_context_when_the_request_raises():
    """A failed request must not bequeath its actor either."""
    middleware = RequestLoggerMiddleware(app=None)

    async def call_next(request: Request) -> PlainTextResponse:
        bind_request_actor_context(request, actor_id="actor-1", tenant_id="tenant-1")
        raise RuntimeError("route exploded")

    with pytest.raises(RuntimeError):
        await middleware.dispatch(Request(_http_scope()), call_next)

    assert _actor_id_var.get() == ""
    assert _tenant_id_var.get() == ""


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
