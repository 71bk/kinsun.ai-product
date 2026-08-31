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

from app.core.correlation import correlation_id_var

# ─── Optional ContextVars for actor/tenant context ───────────────────────────
# These may be set by the auth middleware (downstream). The logger reads them
# on 4xx/5xx responses for auditing purposes.
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
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Extract or generate correlation_id
        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        correlation_id_var.set(correlation_id)

        # 2. Measure duration
        start_time = time.perf_counter()

        # 3. Process the request
        response: Response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        # 4. Emit structured log (best-effort, never interrupts request processing)
        try:
            log_entry: dict = {
                "timestamp": datetime.now(UTC).isoformat(),
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "correlation_id": correlation_id,
            }

            # 5. On error responses, include actor/tenant context for auditing.
            #    Read from request.state (set by auth middleware/dependency) as
            #    the primary source. Fall back to ContextVars for compatibility.
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

        # 6. Attach correlation_id to response headers
        response.headers["x-correlation-id"] = correlation_id

        return response
