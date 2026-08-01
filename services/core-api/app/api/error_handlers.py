"""Structured error handler registration for the Core API.

Maps domain and framework exceptions to consistent ErrorEnvelope responses. In
production mode, internal details (stack traces, SQL, file paths) are stripped
from responses. Framework validation and HTTP errors never echo rejected input
or exception details.

Self-healing: if an error handler itself fails, a minimal 500 response with
only the correlation_id is returned.
"""

from __future__ import annotations

import logging
import re
import traceback
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.envelopes import ErrorBody, ErrorEnvelope, ValidationDetail
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
from app.policies import ActorInactiveError, RoleModeIncompatibleError

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Request-scoped correlation_id. Set by request logging middleware;
# if not yet set when the error handler runs, a new UUID is generated.
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

# Exception class → HTTP status code mapping.
EXCEPTION_MAP: dict[type[DomainException], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 422,
    AuthorizationDeniedError: 404,  # Hide resource existence
    AuthenticationError: 401,
    ServiceUnavailableError: 503,
    TenantScopeError: 401,
    RoleModeIncompatibleError: 403,
    ActorInactiveError: 403,
}

# Human-friendly code slugs for each status.
_STATUS_CODE_SLUGS: dict[int, str] = {
    400: "bad_request",
    401: "authentication_required",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
    503: "service_unavailable",
}

_HTTP_STATUS_MESSAGES: dict[int, str] = {
    400: "Bad request.",
    401: "Authentication required.",
    403: "Forbidden.",
    404: "Resource not found.",
    405: "Method not allowed.",
    409: "Request conflicts with the current resource state.",
    422: "Request validation failed.",
    429: "Too many requests.",
    500: "Internal server error.",
    503: "Service unavailable.",
}

_REASON_CODE_BY_EXCEPTION: dict[type[Exception], str] = {
    NotFoundError: "RESOURCE_NOT_FOUND",
    ConflictError: "VERSION_OR_IDEMPOTENCY_CONFLICT",
    ValidationError: "SCHEMA_OR_SEMANTIC_VALIDATION_FAILED",
    AuthorizationDeniedError: "RESOURCE_NOT_FOUND_OR_FORBIDDEN",
    AuthenticationError: "AUTHENTICATION_FAILED",
    ServiceUnavailableError: "DEPENDENCY_UNAVAILABLE",
    TenantScopeError: "TENANT_SCOPE_INVALID",
    RoleModeIncompatibleError: "ROLE_MODE_INCOMPATIBLE",
    ActorInactiveError: "ACTOR_INACTIVE",
}

# Patterns that indicate internal details unsafe for production responses.
_INTERNAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
    re.compile(r"File \"[^\"]+\",\s*line \d+", re.IGNORECASE),
    re.compile(r"(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\s", re.IGNORECASE),
    re.compile(r"[/\\](app|services|site-packages)[/\\]", re.IGNORECASE),
]


def _get_correlation_id() -> str:
    """Retrieve the current correlation_id or generate a new one."""
    cid = _correlation_id.get()
    if not cid:
        cid = str(uuid.uuid4())
        _correlation_id.set(cid)
    return cid


def _is_production() -> bool:
    """Check if the application is running in production mode."""
    # Import here to avoid circular imports at module load time.
    from app.core.config import AppEnv, get_settings

    try:
        return get_settings().app_env == AppEnv.PRODUCTION
    except Exception:
        # If settings can't be loaded, assume production (safe default).
        return True


def _sanitize_message(message: str) -> str:
    """In production, strip internal details from error messages."""
    if not _is_production():
        return message

    for pattern in _INTERNAL_PATTERNS:
        if pattern.search(message):
            return "An internal error occurred."

    return message


def _build_error_envelope(
    status_code: int,
    message: str,
    correlation_id: str,
    details: list[ValidationDetail] | None = None,
    reason_code: str | None = None,
    retryable: bool = False,
) -> ErrorEnvelope:
    """Construct an ErrorEnvelope for the given status and message."""
    code = _STATUS_CODE_SLUGS.get(status_code, "internal_error")
    safe_message = _sanitize_message(message)

    return ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=safe_message,
            correlation_id=correlation_id,
            reason_code=reason_code,
            retryable=retryable,
            details=details,
        )
    )


async def _domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
    """Handle known domain exceptions by mapping to the correct HTTP status."""
    try:
        correlation_id = _get_correlation_id()
        status_code = EXCEPTION_MAP.get(type(exc), 500)

        # For ValidationError, include field-level details.
        details: list[ValidationDetail] | None = None
        if isinstance(exc, ValidationError) and hasattr(exc, "details"):
            details = [
                ValidationDetail(field=d.get("field", ""), reason=d.get("reason", ""))
                for d in exc.details
            ]

        message = exc.message if exc.message else "An error occurred."
        envelope = _build_error_envelope(
            status_code=status_code,
            message=message,
            correlation_id=correlation_id,
            details=details,
            reason_code=_REASON_CODE_BY_EXCEPTION.get(
                type(exc),
                "UNEXPECTED_DOMAIN_ERROR",
            ),
            retryable=status_code in {500, 502, 503, 504},
        )

        logger.warning(
            "domain_exception",
            extra={
                "correlation_id": correlation_id,
                "exception_type": type(exc).__name__,
                "status_code": status_code,
                "path": request.url.path,
            },
        )

        return JSONResponse(
            status_code=status_code,
            content=envelope.model_dump(mode="json"),
        )
    except Exception as handler_exc:
        # Self-healing: error handler failed — return minimal 500.
        return _fallback_500(request, handler_exc)


async def _request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return an ErrorEnvelope without echoing rejected request data."""
    try:
        correlation_id = _get_correlation_id()
        details = [
            ValidationDetail(field="request", reason="INVALID_REQUEST_FIELD") for _ in exc.errors()
        ]
        envelope = _build_error_envelope(
            status_code=422,
            message="Request validation failed.",
            correlation_id=correlation_id,
            details=details,
            reason_code="REQUEST_VALIDATION_FAILED",
            retryable=False,
        )
        logger.warning(
            "request_validation_exception",
            extra={
                "correlation_id": correlation_id,
                "error_count": len(details),
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=422,
            content=envelope.model_dump(mode="json"),
        )
    except Exception as handler_exc:
        return _fallback_500(request, handler_exc)


async def _http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Wrap framework HTTP errors without leaking their arbitrary detail payload."""
    try:
        correlation_id = _get_correlation_id()
        status_code = exc.status_code
        message = _HTTP_STATUS_MESSAGES.get(
            status_code,
            "Request could not be completed."
            if 400 <= status_code < 500
            else "Internal server error.",
        )
        envelope = _build_error_envelope(
            status_code=status_code,
            message=message,
            correlation_id=correlation_id,
            reason_code=f"HTTP_{status_code}",
            retryable=status_code in {500, 502, 503, 504},
        )
        logger.warning(
            "http_exception",
            extra={
                "correlation_id": correlation_id,
                "status_code": status_code,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=status_code,
            content=envelope.model_dump(mode="json"),
            headers=exc.headers,
        )
    except Exception as handler_exc:
        return _fallback_500(request, handler_exc)


async def _no_authenticator_handler(
    request: Request, exc: NoAuthenticatorConfiguredError
) -> JSONResponse:
    """Return 401 when the service has no authenticator configured.

    NoAuthenticatorConfiguredError is raised while FastAPI resolves the
    authenticator dependency, before any route code runs, and it does not
    derive from DomainException. Without this handler it reaches the catch-all
    and becomes a 500 — but app/middleware/auth.py documents that protected
    endpoints "fail closed (HTTP 401 for all requests)" in exactly this
    situation. A misconfigured deployment must look like an auth failure, not
    like a crash.

    The real reason is logged at critical level and never sent to the client:
    the exception text names the config flag that would enable fake auth.
    """
    try:
        correlation_id = _get_correlation_id()

        logger.critical(
            "no_authenticator_configured",
            extra={
                "correlation_id": correlation_id,
                "path": request.url.path,
                "reason": str(exc),
            },
        )

        envelope = _build_error_envelope(
            status_code=401,
            message="Authentication required.",
            correlation_id=correlation_id,
            reason_code="AUTHENTICATOR_NOT_CONFIGURED",
            retryable=False,
        )

        return JSONResponse(
            status_code=401,
            content=envelope.model_dump(mode="json"),
        )
    except Exception as handler_exc:
        return _fallback_500(request, handler_exc)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle any unhandled exception with a generic 500 response."""
    try:
        correlation_id = _get_correlation_id()

        # Log the full traceback for debugging but never expose it.
        logger.error(
            "unhandled_exception",
            extra={
                "correlation_id": correlation_id,
                "exception_type": type(exc).__name__,
                "path": request.url.path,
                "traceback": traceback.format_exc(),
            },
        )

        envelope = _build_error_envelope(
            status_code=500,
            message="Internal server error.",
            correlation_id=correlation_id,
            reason_code="UNEXPECTED_INTERNAL_ERROR",
            retryable=True,
        )

        return JSONResponse(
            status_code=500,
            content=envelope.model_dump(mode="json"),
        )
    except Exception as handler_exc:
        # Self-healing: error handler failed — return minimal 500.
        return _fallback_500(request, handler_exc)


def _fallback_500(request: Request, handler_exc: Exception) -> JSONResponse:
    """Last-resort 500 response when an error handler itself fails.

    Returns only a correlation_id and generic error code. Never exposes
    details of the secondary failure.
    """
    correlation_id = ""
    try:
        correlation_id = _get_correlation_id()
    except Exception:
        correlation_id = str(uuid.uuid4())

    # Log the handler failure for diagnosis.
    try:
        logger.critical(
            "error_handler_failure",
            extra={
                "correlation_id": correlation_id,
                "handler_exception": str(handler_exc),
                "path": getattr(request, "url", None) and request.url.path,
            },
        )
    except Exception:
        pass  # Absolutely must not fail here.

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Internal server error.",
                "correlation_id": correlation_id,
                "reason_code": "ERROR_HANDLER_FAILURE",
                "retryable": True,
                "details": None,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all Core API error handlers.

    Registers handlers for domain errors, FastAPI request validation, Starlette
    HTTP errors, authenticator misconfiguration, and unexpected exceptions.
    """
    # Register a handler for the base DomainException — this catches all
    # subclasses including those in EXCEPTION_MAP.
    app.add_exception_handler(DomainException, _domain_exception_handler)  # type: ignore[arg-type]

    # Framework-originated errors must use the same safe envelope as routes.
    app.add_exception_handler(
        RequestValidationError,
        _request_validation_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        StarletteHTTPException,
        _http_exception_handler,  # type: ignore[arg-type]
    )

    # Misconfiguration must fail closed as 401, not surface as a 500.
    app.add_exception_handler(
        NoAuthenticatorConfiguredError,
        _no_authenticator_handler,  # type: ignore[arg-type]
    )

    # Catch-all for truly unexpected exceptions.
    app.add_exception_handler(Exception, _unhandled_exception_handler)  # type: ignore[arg-type]
