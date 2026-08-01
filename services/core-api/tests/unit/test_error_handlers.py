"""Unit tests for app.api.error_handlers module.

Validates:
- Exception-to-status mapping (Requirement 9.1, 9.2, 9.3)
- ErrorEnvelope construction with correlation_id (Requirement 8.4, 8.5)
- Production mode strips internal details (Requirement 8.6)
- Self-healing: error handler failure returns minimal 500 (Requirement 9.4)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.api.error_handlers import (
    EXCEPTION_MAP,
    _build_error_envelope,
    _correlation_id,
    _domain_exception_handler,
    _fallback_500,
    _get_correlation_id,
    _sanitize_message,
    _unhandled_exception_handler,
    register_exception_handlers,
)
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationDeniedError,
    ConflictError,
    DomainException,
    NotFoundError,
    ServiceUnavailableError,
    TenantScopeError,
    ValidationError,
)
from app.middleware.auth import NoAuthenticatorConfiguredError


class TestExceptionMap:
    """Tests for the EXCEPTION_MAP dictionary."""

    def test_not_found_maps_to_404(self) -> None:
        assert EXCEPTION_MAP[NotFoundError] == 404

    def test_conflict_maps_to_409(self) -> None:
        assert EXCEPTION_MAP[ConflictError] == 409

    def test_validation_error_maps_to_422(self) -> None:
        assert EXCEPTION_MAP[ValidationError] == 422

    def test_authorization_denied_maps_to_404_not_403(self) -> None:
        """AuthorizationDeniedError returns 404 to hide resource existence."""
        assert EXCEPTION_MAP[AuthorizationDeniedError] == 404

    def test_authentication_error_maps_to_401(self) -> None:
        assert EXCEPTION_MAP[AuthenticationError] == 401

    def test_service_unavailable_maps_to_503(self) -> None:
        assert EXCEPTION_MAP[ServiceUnavailableError] == 503

    def test_tenant_scope_error_maps_to_401(self) -> None:
        assert EXCEPTION_MAP[TenantScopeError] == 401


class TestGetCorrelationId:
    """Tests for _get_correlation_id."""

    def test_generates_uuid_when_not_set(self) -> None:
        token = _correlation_id.set("")
        try:
            cid = _get_correlation_id()
            assert cid  # non-empty
            assert len(cid) == 36  # UUID format
        finally:
            _correlation_id.reset(token)

    def test_returns_existing_correlation_id(self) -> None:
        token = _correlation_id.set("test-correlation-id")
        try:
            cid = _get_correlation_id()
            assert cid == "test-correlation-id"
        finally:
            _correlation_id.reset(token)


class TestSanitizeMessage:
    """Tests for _sanitize_message in production mode."""

    @patch("app.api.error_handlers._is_production", return_value=False)
    def test_returns_original_message_in_development(self, _mock: MagicMock) -> None:
        msg = 'File "/app/services/core-api/app/main.py", line 10'
        assert _sanitize_message(msg) == msg

    @patch("app.api.error_handlers._is_production", return_value=True)
    def test_strips_traceback_in_production(self, _mock: MagicMock) -> None:
        msg = "Traceback (most recent call last): something"
        assert _sanitize_message(msg) == "An internal error occurred."

    @patch("app.api.error_handlers._is_production", return_value=True)
    def test_strips_file_paths_in_production(self, _mock: MagicMock) -> None:
        msg = 'File "/app/services/core-api/main.py", line 42'
        assert _sanitize_message(msg) == "An internal error occurred."

    @patch("app.api.error_handlers._is_production", return_value=True)
    def test_strips_sql_in_production(self, _mock: MagicMock) -> None:
        msg = "SELECT * FROM users WHERE id = 1"
        assert _sanitize_message(msg) == "An internal error occurred."

    @patch("app.api.error_handlers._is_production", return_value=True)
    def test_strips_internal_paths_in_production(self, _mock: MagicMock) -> None:
        msg = "Error in /app/core/something.py"
        assert _sanitize_message(msg) == "An internal error occurred."

    @patch("app.api.error_handlers._is_production", return_value=True)
    def test_safe_message_passes_through_in_production(self, _mock: MagicMock) -> None:
        msg = "Entity not found"
        assert _sanitize_message(msg) == "Entity not found"


class TestBuildErrorEnvelope:
    """Tests for _build_error_envelope."""

    @patch("app.api.error_handlers._is_production", return_value=False)
    def test_builds_envelope_with_correct_code(self, _mock: MagicMock) -> None:
        envelope = _build_error_envelope(404, "Not found", "cid-123")
        assert envelope.error.code == "not_found"
        assert envelope.error.message == "Not found"
        assert envelope.error.correlation_id == "cid-123"

    @patch("app.api.error_handlers._is_production", return_value=False)
    def test_builds_envelope_with_validation_details(self, _mock: MagicMock) -> None:
        from app.core.envelopes import ValidationDetail

        details = [ValidationDetail(field="email", reason="Invalid")]
        envelope = _build_error_envelope(422, "Validation failed", "cid-456", details)
        assert envelope.error.details is not None
        assert len(envelope.error.details) == 1
        assert envelope.error.details[0].field == "email"

    @patch("app.api.error_handlers._is_production", return_value=False)
    def test_unknown_status_defaults_to_internal_error(self, _mock: MagicMock) -> None:
        envelope = _build_error_envelope(418, "I'm a teapot", "cid-789")
        assert envelope.error.code == "internal_error"


class TestDomainExceptionHandler:
    """Tests for _domain_exception_handler."""

    def _make_request(self, path: str = "/test") -> MagicMock:
        request = MagicMock()
        request.url.path = path
        return request

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_not_found_returns_404(self, _mock: MagicMock) -> None:
        request = self._make_request()
        token = _correlation_id.set("test-cid")
        try:
            response = await _domain_exception_handler(request, NotFoundError("Entity missing"))
            assert response.status_code == 404
        finally:
            _correlation_id.reset(token)

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_authorization_denied_returns_404(self, _mock: MagicMock) -> None:
        """AuthorizationDeniedError maps to 404 to hide resource existence."""
        request = self._make_request()
        token = _correlation_id.set("test-cid")
        try:
            response = await _domain_exception_handler(
                request, AuthorizationDeniedError("access denied")
            )
            assert response.status_code == 404
        finally:
            _correlation_id.reset(token)

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_validation_error_returns_422_with_details(self, _mock: MagicMock) -> None:
        request = self._make_request()
        token = _correlation_id.set("test-cid")
        try:
            exc = ValidationError(
                [{"field": "name", "reason": "Required"}, {"field": "age", "reason": "Invalid"}]
            )
            response = await _domain_exception_handler(request, exc)
            assert response.status_code == 422
            import json

            body = json.loads(response.body.decode())
            assert body["error"]["details"] is not None
            assert len(body["error"]["details"]) == 2
            assert body["error"]["details"][0]["field"] == "name"
        finally:
            _correlation_id.reset(token)

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_authentication_error_returns_401(self, _mock: MagicMock) -> None:
        request = self._make_request()
        token = _correlation_id.set("test-cid")
        try:
            response = await _domain_exception_handler(
                request, AuthenticationError("Invalid token")
            )
            assert response.status_code == 401
        finally:
            _correlation_id.reset(token)

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_service_unavailable_returns_503(self, _mock: MagicMock) -> None:
        request = self._make_request()
        token = _correlation_id.set("test-cid")
        try:
            response = await _domain_exception_handler(request, ServiceUnavailableError("DB down"))
            assert response.status_code == 503
        finally:
            _correlation_id.reset(token)

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_tenant_scope_error_returns_401(self, _mock: MagicMock) -> None:
        request = self._make_request()
        token = _correlation_id.set("test-cid")
        try:
            response = await _domain_exception_handler(request, TenantScopeError("No tenant"))
            assert response.status_code == 401
        finally:
            _correlation_id.reset(token)

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_response_includes_correlation_id(self, _mock: MagicMock) -> None:
        request = self._make_request()
        token = _correlation_id.set("my-correlation-id")
        try:
            response = await _domain_exception_handler(request, NotFoundError("gone"))
            import json

            body = json.loads(response.body.decode())
            assert body["error"]["correlation_id"] == "my-correlation-id"
        finally:
            _correlation_id.reset(token)


class TestUnhandledExceptionHandler:
    """Tests for _unhandled_exception_handler."""

    def _make_request(self, path: str = "/test") -> MagicMock:
        request = MagicMock()
        request.url.path = path
        return request

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_returns_500(self, _mock: MagicMock) -> None:
        request = self._make_request()
        token = _correlation_id.set("unhandled-cid")
        try:
            response = await _unhandled_exception_handler(request, RuntimeError("boom"))
            assert response.status_code == 500
        finally:
            _correlation_id.reset(token)

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_returns_generic_message(self, _mock: MagicMock) -> None:
        request = self._make_request()
        token = _correlation_id.set("unhandled-cid")
        try:
            response = await _unhandled_exception_handler(request, RuntimeError("secret details"))
            import json

            body = json.loads(response.body.decode())
            assert body["error"]["message"] == "Internal server error."
            assert "secret details" not in json.dumps(body)
        finally:
            _correlation_id.reset(token)

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_includes_correlation_id(self, _mock: MagicMock) -> None:
        request = self._make_request()
        token = _correlation_id.set("unhandled-cid-2")
        try:
            response = await _unhandled_exception_handler(request, RuntimeError("oops"))
            import json

            body = json.loads(response.body.decode())
            assert body["error"]["correlation_id"] == "unhandled-cid-2"
        finally:
            _correlation_id.reset(token)


class TestFallback500:
    """Tests for _fallback_500 (self-healing last-resort handler)."""

    def test_returns_500_with_correlation_id(self) -> None:
        request = MagicMock()
        request.url.path = "/broken"
        token = _correlation_id.set("fallback-cid")
        try:
            response = _fallback_500(request, RuntimeError("handler broke"))
            assert response.status_code == 500
            import json

            body = json.loads(response.body.decode())
            assert body["error"]["correlation_id"] == "fallback-cid"
            assert body["error"]["code"] == "internal_error"
            assert "handler broke" not in json.dumps(body)
        finally:
            _correlation_id.reset(token)


class TestFrameworkExceptionHandlers:
    """Tests for safe FastAPI and Starlette exception translation."""

    def _make_request(self, path: str = "/test") -> MagicMock:
        request = MagicMock()
        request.url.path = path
        return request

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_request_validation_never_echoes_rejected_input(self, _mock: MagicMock) -> None:
        from fastapi.exceptions import RequestValidationError

        from app.api.error_handlers import _request_validation_exception_handler

        request = self._make_request()
        exc = RequestValidationError(
            [
                {
                    "type": "string_too_long",
                    "loc": ("body", "notes"),
                    "msg": "String should have at most 10 characters",
                    "input": "restricted input must not be returned",
                }
            ]
        )

        response = await _request_validation_exception_handler(request, exc)

        import json

        body = json.loads(response.body.decode())
        assert response.status_code == 422
        assert body["error"]["reason_code"] == "REQUEST_VALIDATION_FAILED"
        assert body["error"]["details"] == [{"field": "request", "reason": "INVALID_REQUEST_FIELD"}]
        assert "restricted input must not be returned" not in json.dumps(body)

    @pytest.mark.asyncio
    @patch("app.api.error_handlers._is_production", return_value=False)
    async def test_http_exception_never_echoes_detail_payload(self, _mock: MagicMock) -> None:
        from starlette.exceptions import HTTPException as StarletteHTTPException

        from app.api.error_handlers import _http_exception_handler

        response = await _http_exception_handler(
            self._make_request(),
            StarletteHTTPException(
                status_code=405,
                detail={"restricted": "must not be returned"},
            ),
        )

        import json

        body = json.loads(response.body.decode())
        assert response.status_code == 405
        assert body["error"]["code"] == "method_not_allowed"
        assert body["error"]["reason_code"] == "HTTP_405"
        assert "must not be returned" not in json.dumps(body)


class TestRegisterExceptionHandlers:
    """Tests for register_exception_handlers."""

    def test_registers_domain_framework_and_catch_all_handlers(self) -> None:
        from fastapi.exceptions import RequestValidationError
        from starlette.exceptions import HTTPException as StarletteHTTPException

        app = MagicMock()
        register_exception_handlers(app)

        assert app.add_exception_handler.call_count == 5
        registered_types = {call.args[0] for call in app.add_exception_handler.call_args_list}
        assert DomainException in registered_types
        assert RequestValidationError in registered_types
        assert StarletteHTTPException in registered_types
        assert NoAuthenticatorConfiguredError in registered_types
        assert Exception in registered_types
