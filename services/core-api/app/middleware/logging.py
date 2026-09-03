"""Structured request logging middleware with correlation ID propagation.

Logs a structured JSON entry for every HTTP request, extracts or generates
a correlation_id (UUID v4), and propagates it via contextvars for downstream
consumers (other middleware, handlers, repositories, etc.).

Security:
    - NEVER logs request/response bodies
    - NEVER logs authorization headers, cookies, or x-api-key values
    - NEVER logs sensitive query parameters

Usage:
    from app.core.correlation import correlation_id_var

    # Read the current correlation_id in any async context:
    cid = correlation_id_var.get()

    # Authentication binds the actor/tenant that 4xx/5xx entries are audited
    # against; see bind_request_actor_context() and app/middleware/auth.py.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.correlation import correlation_id_var, resolve_correlation_id

# ─── Request-scoped audit context ────────────────────────────────────────────
# Populated by bind_request_actor_context() as soon as authentication succeeds.
# request.state is the primary carrier because it lives on the ASGI scope and
# therefore survives the BaseHTTPMiddleware task boundary; these ContextVars are
# the fallback for code that only has the ambient context to work with.
_actor_id_var: ContextVar[str] = ContextVar("actor_id", default="")
_tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")

# ─── Headers/params that must NEVER appear in logs ───────────────────────────
SENSITIVE_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "cookie",
        "x-api-key",
        "x-kinsun-service-credential",
    }
)

logger = logging.getLogger("app.request")


def _audit_id(value: uuid.UUID | str | None) -> str:
    """Normalise an identifier to the string form used in log entries."""
    return "" if value is None else str(value)


def bind_request_actor_context(
    request: Request,
    *,
    actor_id: uuid.UUID | str | None,
    tenant_id: uuid.UUID | str | None,
) -> None:
    """Record the authenticated actor and tenant for this request's audit log.

    Called by the authentication dependency the moment authentication succeeds,
    which is the only point where a trusted actor and tenant exist and the
    request has not yet been able to fail. Without it an authenticated request
    that is later denied by policy, rejected as a domain error, or crashed
    produces an anonymous 4xx/5xx log line — precisely the entry an incident
    investigation needs to attribute.

    Never trust client-supplied values here: the caller must pass the resolved
    ``ActorContext``, not anything read from headers or the request body.
    """
    actor = _audit_id(actor_id)
    tenant = _audit_id(tenant_id)

    request.state.actor_id = actor
    request.state.tenant_id = tenant
    _actor_id_var.set(actor)
    _tenant_id_var.set(tenant)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Log structured JSON for every HTTP request.

    Responsibilities:
        1. Extract ``x-correlation-id`` from request headers, or generate a UUID v4.
        2. Store the correlation_id in a ContextVar for downstream propagation.
        3. Measure request duration using ``time.perf_counter()``.
        4. Emit a structured log entry (JSON-compatible dict via ``extra``).
        5. Attach ``x-correlation-id`` to the response headers.
        6. On 4xx/5xx responses, include tenant_id and actor_id if available.
        7. If log emission fails, swallow the error silently.
        8. Clear the audit ContextVars again once the request ends.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Extract or generate correlation_id
        correlation_id = resolve_correlation_id(request.headers.get("x-correlation-id"))
        correlation_id_var.set(correlation_id)

        # 2. Start every request from an empty audit context, and restore the
        #    previous one in the finally block below. A ContextVar left behind
        #    by an earlier request sharing this context would otherwise let one
        #    request be logged against another request's actor.
        actor_token = _actor_id_var.set("")
        tenant_token = _tenant_id_var.set("")

        # 3. Measure duration
        start_time = time.perf_counter()

        try:
            # 4. Process the request
            response: Response = await call_next(request)

            duration_ms = (time.perf_counter() - start_time) * 1000

            # 5. Emit structured log (best-effort, never interrupts processing)
            try:
                log_entry: dict = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "correlation_id": correlation_id,
                }

                # 6. On error responses, include actor/tenant context for
                #    auditing. request.state is the primary source because
                #    bind_request_actor_context() writes it onto the ASGI scope
                #    shared with the downstream task; the ContextVars are the
                #    fallback for callers that only set the ambient context.
                if response.status_code >= 400:
                    tenant_id = getattr(request.state, "tenant_id", None) or _tenant_id_var.get()
                    actor_id = getattr(request.state, "actor_id", None) or _actor_id_var.get()
                    if tenant_id:
                        log_entry["tenant_id"] = tenant_id
                    if actor_id:
                        log_entry["actor_id"] = actor_id

                logger.info("request_completed", extra=log_entry)
            except Exception:  # noqa: BLE001
                # Log emission failure must NOT interrupt request processing.
                pass

            # 7. Attach correlation_id to response headers
            response.headers["x-correlation-id"] = correlation_id

            return response
        finally:
            # 8. Release the audit context even when the request raised, so a
            #    failed request cannot bequeath its actor to the next one.
            _actor_id_var.reset(actor_token)
            _tenant_id_var.reset(tenant_token)
