"""Environment-guarded authentication factory and FastAPI dependency.

Defines:
- FakeAuthenticator: configurable authenticator for tests and local dev
- NoAuthenticatorConfiguredError: raised when no auth is configured
- get_authenticator(): environment-guarded factory
- get_actor_context(): FastAPI dependency for protected routes
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from fastapi import Depends, Request

from app.core.auth import ActorContext, AuthenticationRequest, Authenticator
from app.core.config import AppEnv, get_settings
from app.core.exceptions import AuthenticationError, ServiceUnavailableError
from app.core.oidc import GoogleTokenVerifier, LineTokenVerifier
from app.middleware.logging import bind_request_actor_context


class FakeAuthenticator(Authenticator):
    """Test/dev authenticator returning configurable ActorContext.

    Safety:
    - MAY be used in tests (always, via dependency override).
    - MAY be enabled in local development (APP_ENV=development)
      with explicit FAKE_AUTH_ENABLED=true config flag.
    - MUST NEVER be active in production.
    """

    def __init__(
        self,
        actor_id: uuid.UUID | None = None,
        actor_role: str = "care_worker",
        tenant_id: uuid.UUID | None = None,
        status: str = "ACTIVE",
    ) -> None:
        self._actor_id = actor_id or uuid.uuid4()
        self._actor_role = actor_role
        self._tenant_id = tenant_id or uuid.uuid4()
        self._status = status

    async def authenticate(self, request: AuthenticationRequest) -> ActorContext:
        return ActorContext(
            actor_id=self._actor_id,
            actor_role=self._actor_role,
            tenant_id=self._tenant_id,
            status=self._status,
        )


class NoAuthenticatorConfiguredError(Exception):
    """Raised at startup when no real authenticator is configured.

    In production this means protected endpoints will fail closed (401).
    """

    pass


def get_authenticator() -> Authenticator:
    """Factory function for resolving the active authenticator.

    Rules:
    - In tests: FakeAuthenticator is injected via FastAPI dependency override.
      This function is never called directly in tests.
    - In development (APP_ENV=development) with FAKE_AUTH_ENABLED=true:
      Returns FakeAuthenticator for local dev convenience.
    - In production (APP_ENV=production):
      Returns the configured real authenticator.
      If no real authenticator is configured, raises
      NoAuthenticatorConfiguredError — protected endpoints will
      fail closed (HTTP 401 for all requests).
    - NEVER defaults to FakeAuthenticator in production.
    """
    settings = get_settings()

    if settings.app_env == AppEnv.PRODUCTION:
        # In production: require a real authenticator or fail closed
        real_authenticator = _resolve_production_authenticator(settings)
        if real_authenticator is None:
            raise NoAuthenticatorConfiguredError(
                "No authenticator configured for production. "
                "Protected endpoints will reject all requests."
            )
        return real_authenticator

    # Development mode
    if settings.fake_auth_enabled:
        if settings.fake_auth_actor_id is None or settings.fake_auth_tenant_id is None:
            raise NoAuthenticatorConfiguredError(
                "Fake authentication requires server-side actor and tenant IDs"
            )
        return FakeAuthenticator(
            actor_id=settings.fake_auth_actor_id,
            actor_role=settings.fake_auth_actor_role,
            tenant_id=settings.fake_auth_tenant_id,
        )

    # Development without fake auth — still require real config or fail
    real_authenticator = _resolve_production_authenticator(settings)
    if real_authenticator is None:
        raise NoAuthenticatorConfiguredError(
            "No authenticator configured. Set FAKE_AUTH_ENABLED=true "
            "for local development or configure a real authenticator."
        )
    return real_authenticator


def _resolve_production_authenticator(settings) -> Authenticator | None:
    """Build the explicitly enabled Core-owned App Session authenticator."""
    if getattr(settings, "app_session_auth_enabled", False) is not True:
        return None
    from app.adapters.auth.app_session import DatabaseAppSessionAuthenticator
    from app.db.session import get_db_engine

    return DatabaseAppSessionAuthenticator(get_db_engine(), settings)


def get_google_token_verifier() -> GoogleTokenVerifier:
    """Return the verifier used only by the unbound Google handoff endpoint."""
    settings = get_settings()
    if not settings.google_oidc_client_id:
        raise ServiceUnavailableError("Google identity handoff is unavailable")
    try:
        return _build_google_token_verifier(
            settings.google_oidc_client_id,
            settings.google_oidc_jwks_cache_seconds,
            settings.google_oidc_http_timeout_seconds,
        )
    except ValueError as exc:
        raise ServiceUnavailableError("Google identity handoff is unavailable") from exc


def get_line_token_verifier() -> LineTokenVerifier:
    """Return the verifier used only by the unbound LINE handoff endpoint."""
    settings = get_settings()
    if not settings.line_login_channel_id:
        raise ServiceUnavailableError("LINE identity handoff is unavailable")
    try:
        return _build_line_token_verifier(
            settings.line_login_channel_id,
            settings.line_oidc_http_timeout_seconds,
        )
    except ValueError as exc:
        raise ServiceUnavailableError("LINE identity handoff is unavailable") from exc


@lru_cache(maxsize=16)
def _build_line_token_verifier(
    channel_id: str,
    http_timeout_seconds: float,
) -> LineTokenVerifier:
    from app.adapters.auth.line_oidc import LineOidcEndpointVerifier

    return LineOidcEndpointVerifier(
        channel_id=channel_id,
        timeout_seconds=http_timeout_seconds,
    )


@lru_cache(maxsize=16)
def _build_google_token_verifier(
    client_id: str,
    jwks_cache_seconds: int,
    http_timeout_seconds: float,
) -> GoogleTokenVerifier:
    from app.adapters.auth.google_oidc import GoogleOidcJwtVerifier

    return GoogleOidcJwtVerifier(
        client_id=client_id,
        jwks_cache_seconds=jwks_cache_seconds,
        http_timeout_seconds=http_timeout_seconds,
    )


async def get_actor_context(
    request: Request,
    authenticator: Authenticator = Depends(get_authenticator),
) -> ActorContext:
    """FastAPI dependency for protected routes.

    Calls the authenticator to resolve the actor's identity. On failure,
    raises AuthenticationError which maps to HTTP 401.

    On success the resolved actor and tenant are bound to the request's audit
    context. This is the only place every protected route passes through with a
    trusted identity in hand, so binding here is what lets the request logger
    attribute a later authorization denial, domain error or crash to the caller
    instead of emitting an anonymous 4xx/5xx line. A failed authentication is
    deliberately left unbound — there is no trusted identity to record.
    """
    try:
        actor_context = await authenticator.authenticate(request)
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError("Authentication failed") from exc

    bind_request_actor_context(
        request,
        actor_id=actor_context.actor_id,
        tenant_id=actor_context.tenant_id,
    )
    return actor_context
