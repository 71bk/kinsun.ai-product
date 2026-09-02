"""Application entrypoint with lifespan management.

Creates the FastAPI application, manages startup and shutdown lifecycle,
and wires together all core components in a defined initialization order.

Startup order:
    1. Settings (validated configuration)
    2. DatabaseEngine (connection pool)
    3. Connectivity check (non-fatal — degraded mode if DB unreachable)
    4. Middleware registration
    5. Route registration

Shutdown order:
    Reverse of startup — dispose database engine (30s timeout).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.agent_runs import router as agent_runs_router
from app.api.app_sessions import router as app_sessions_router
from app.api.assignments import router as assignments_router
from app.api.assisted_elders import router as assisted_elders_router
from app.api.care_actions import router as care_actions_router
from app.api.care_events import router as care_events_router
from app.api.consents import router as consents_router
from app.api.deletions import router as deletions_router
from app.api.elders import router as elders_router
from app.api.error_handlers import register_exception_handlers
from app.api.family_invitations import router as family_invitations_router
from app.api.google_oidc_handoff import router as google_oidc_handoff_router
from app.api.health import router as health_router
from app.api.identity import router as identity_router
from app.api.kinsun_email_auth import router as kinsun_email_auth_router
from app.api.line_links import router as line_links_router
from app.api.line_oidc_handoff import router as line_oidc_handoff_router
from app.api.line_webhook import router as line_webhook_router
from app.api.memories import router as memories_router
from app.api.notifications import router as notifications_router
from app.api.ready import router as ready_router
from app.api.reports import router as reports_router
from app.api.summaries import router as summaries_router
from app.api.tools import router as tools_router
from app.api.voice_sessions import router as voice_sessions_router
from app.core.config import AppEnv, get_settings
from app.core.log_safety import exception_type_name, record_exception
from app.db.engine import DatabaseEngine
from app.db.session import init_db_engine
from app.middleware.logging import RequestLoggerMiddleware

logger = logging.getLogger(__name__)


def _invalid_setting_names(exc: Exception) -> list[str]:
    """Return the setting names a validation failure blames — never their values.

    Pydantic renders the rejected input inside ``str(exc)``, and DATABASE_URL
    carries the database password, so a settings failure is reduced to its error
    locations here instead of being formatted anywhere it could be logged or
    printed. An error object that is not the Pydantic shape yields no names
    rather than a fallback that might quote it.
    """
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return []

    try:
        located = {".".join(str(part) for part in error.get("loc", ())) for error in errors()}
    except Exception:  # noqa: BLE001
        return []
    return sorted(name for name in located if name)


def _settings_failure_notice(invalid_fields: list[str]) -> str:
    """Compose the stderr line for a fatal settings failure without any value."""
    named = ", ".join(invalid_fields) if invalid_fields else "unknown setting"
    return f"FATAL: Settings validation failed for: {named}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Ordered startup and shutdown lifecycle.

    Startup:
        1. Load and validate Settings (fatal if invalid — exit non-zero)
        2. Create DatabaseEngine from settings
        3. Check DB connectivity (non-fatal — degraded mode)
        4. Store engine in app.state + init session dependency
        5. Log ready message

    Shutdown:
        Dispose database engine with 30s timeout.
    """
    # ── Step 1: Load settings ────────────────────────────────────────────────
    # If settings fail to load (e.g., invalid DATABASE_URL), this raises
    # a Pydantic ValidationError which propagates and causes process exit.
    try:
        settings = get_settings()
    except Exception as exc:
        # Neither the log nor stderr may carry the exception text: a Pydantic
        # ValidationError echoes the rejected input, and the value most likely
        # to be rejected is DATABASE_URL with its password. Field names are
        # enough to fix the deployment, and no traceback is sent to the
        # diagnostics sink either, because it would quote the same input.
        invalid_fields = _invalid_setting_names(exc)
        logger.critical(
            "fatal_startup_error",
            extra={
                "component": "Settings",
                "code": "SETTINGS_VALIDATION_FAILED",
                "exception_type": exception_type_name(exc),
                "invalid_fields": invalid_fields,
            },
        )
        print(_settings_failure_notice(invalid_fields), file=sys.stderr)
        sys.exit(1)

    # ── Step 2: Create DatabaseEngine ────────────────────────────────────────
    db_engine = DatabaseEngine(settings)

    # ── Step 3: Check DB connectivity (non-fatal) ────────────────────────────
    try:
        connected = await db_engine.recover_connectivity()
        if not connected:
            logger.warning(
                "db_startup_degraded",
                extra={
                    "component": "DatabaseEngine",
                    "detail": "Database unreachable at startup — running in degraded mode",
                },
            )
    except Exception as exc:
        # A connection failure names the host, user and sometimes the DSN, so
        # only the exception type reaches the general log; the traceback goes to
        # the controlled diagnostics sink.
        logger.warning(
            "db_startup_failed",
            extra={
                "component": "DatabaseEngine",
                "code": "DB_STARTUP_CONNECTIVITY_FAILED",
                "exception_type": exception_type_name(exc),
                "detail": "Database unreachable at startup — running in degraded mode",
            },
        )
        record_exception("DB_STARTUP_CONNECTIVITY_FAILED", exc, component="DatabaseEngine")
        # Readiness remains false; a later DB-backed request may run one bounded retry.

    # ── Step 4: Wire engine into app state and session dependency ─────────────
    app.state.db_engine = db_engine
    app.state.settings = settings
    init_db_engine(db_engine)

    # ── Step 5: Log ready message ────────────────────────────────────────────
    logger.info(
        "app_ready",
        extra={
            "host": settings.host,
            "port": settings.port,
            "app_env": settings.app_env.value,
        },
    )

    yield

    # ── Shutdown: dispose engine (reverse order) ─────────────────────────────
    await db_engine.dispose(timeout=30.0)
    logger.info("app_shutdown_complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    - Title, version from settings
    - OpenAPI docs enabled only in development (404 in production)
    - Registers middleware, routes, and exception handlers
    """
    # Load settings for app construction (title, docs configuration).
    # If this fails, the process should exit fast.
    try:
        settings = get_settings()
    except Exception as exc:
        # Same rule as in lifespan(): the rejected value never reaches stderr.
        print(_settings_failure_notice(_invalid_setting_names(exc)), file=sys.stderr)
        sys.exit(1)

    # In production, disable OpenAPI docs (404 for /docs, /redoc, /openapi.json)
    if settings.app_env == AppEnv.PRODUCTION:
        docs_url = None
        redoc_url = None
        openapi_url = None
    else:
        docs_url = settings.docs_url
        redoc_url = "/redoc"
        openapi_url = "/openapi.json"

    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    # ── Register middleware (outermost first) ────────────────────────────────
    app.add_middleware(RequestLoggerMiddleware)

    # ── Register routes ──────────────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(ready_router)
    app.include_router(line_webhook_router)
    app.include_router(line_links_router)
    app.include_router(identity_router)
    app.include_router(elders_router)
    app.include_router(assisted_elders_router)
    app.include_router(family_invitations_router)
    app.include_router(consents_router)
    app.include_router(deletions_router)
    app.include_router(voice_sessions_router)
    app.include_router(care_actions_router)
    app.include_router(care_events_router)
    app.include_router(memories_router)
    app.include_router(notifications_router)
    app.include_router(summaries_router)
    app.include_router(reports_router)
    app.include_router(assignments_router)
    app.include_router(agent_runs_router)
    app.include_router(tools_router)
    if settings.app_session_auth_enabled:
        app.include_router(app_sessions_router)
    if settings.kinsun_native_auth_enabled:
        app.include_router(kinsun_email_auth_router)
    if settings.google_oidc_handoff_enabled:
        app.include_router(google_oidc_handoff_router)
    if settings.line_oidc_handoff_enabled:
        app.include_router(line_oidc_handoff_router)

    # ── Register exception handlers ──────────────────────────────────────────
    register_exception_handlers(app)

    return app


# Module-level app instance used by uvicorn (uvicorn app.main:app)
app = create_app()
