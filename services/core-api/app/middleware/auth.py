"""Authentication abstractions and environment-guarded factory.

Defines:
- ActorContext: immutable identity derived from authentication
- Authenticator ABC: pluggable interface for auth providers
- FakeAuthenticator: configurable authenticator for tests and local dev
- NoAuthenticatorConfiguredError: raised when no auth is configured
- get_authenticator(): environment-guarded factory
- get_actor_context(): FastAPI dependency for protected routes
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Depends, Request

from app.core.config import AppEnv, get_settings
from app.core.exceptions import AuthenticationError, ServiceUnavailableError

if TYPE_CHECKING:
    from app.adapters.auth.cognito import CognitoTokenVerifier
    from app.adapters.auth.google_oidc import GoogleTokenVerifier
    from app.adapters.auth.line_oidc import LineTokenVerifier


@dataclass(frozen=True)
class ActorContext:
    """Immutable identity context derived from authentication.

    Actor identity is derived ONLY from the authenticator — never from
    request body, query parameters, or headers directly.
    """

    actor_id: uuid.UUID
    actor_role: str
    tenant_id: uuid.UUID
    status: str = "ACTIVE"


class Authenticator(ABC):
    """Pluggable authenticator interface.

    Concrete implementations:
    - FakeAuthenticator (tests + explicit local dev)
    - CognitoAuthenticator (future production spec)
    """

    @abstractmethod
    async def authenticate(self, request: Request) -> ActorContext:
        """Extract and validate credentials, return ActorContext.

        Raises:
            AuthenticationError: if credentials are missing or invalid.
        """
        ...


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

    async def authenticate(self, request: Request) -> ActorContext:
        return ActorContext(
            actor_id=self._actor_id,
            actor_role=self._actor_role,
            tenant_id=self._tenant_id,
            status=self._status,
        )


class RoutedAuthenticator(Authenticator):
    """Route versioned App Session credentials without downgrade fallback."""

    def __init__(
        self,
        *,
        app_session: Authenticator | None,
        cognito: Authenticator | None,
    ) -> None:
        self._app_session = app_session
        self._cognito = cognito

    async def authenticate(self, request: Request) -> ActorContext:
        token = _peek_bearer_token(request)
        if token.startswith("ks1_"):
            if self._app_session is None:
                raise AuthenticationError("Authentication required")
            return await self._app_session.authenticate(request)
        if self._cognito is None:
            raise AuthenticationError("Authentication required")
        return await self._cognito.authenticate(request)


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
    """Build explicitly enabled auth runtimes without downgrade fallback."""
    from app.db.session import get_db_engine

    app_session_authenticator: Authenticator | None = None
    if getattr(settings, "app_session_auth_enabled", False) is True:
        from app.adapters.auth.app_session import DatabaseAppSessionAuthenticator

        app_session_authenticator = DatabaseAppSessionAuthenticator(get_db_engine(), settings)

    cognito_authenticator: Authenticator | None = None
    if getattr(settings, "cognito_auth_enabled", False) is True:
        from app.adapters.auth.cognito import (
            CognitoAuthenticator,
            DatabaseCognitoActorContextResolver,
        )

        verifier = _get_cognito_token_verifier_from_settings(settings)
        cognito_authenticator = CognitoAuthenticator(
            verifier,
            DatabaseCognitoActorContextResolver(get_db_engine().session_factory),
        )

    if app_session_authenticator is None and cognito_authenticator is None:
        return None
    if app_session_authenticator is None:
        return cognito_authenticator
    if cognito_authenticator is None:
        return app_session_authenticator
    return RoutedAuthenticator(
        app_session=app_session_authenticator,
        cognito=cognito_authenticator,
    )


def _peek_bearer_token(request: Request) -> str:
    values = request.headers.getlist("authorization")
    if len(values) != 1:
        raise AuthenticationError("Authentication required")
    scheme, separator, token = values[0].partition(" ")
    if (
        separator != " "
        or scheme.casefold() != "bearer"
        or not token
        or len(token) > 16_384
        or any(character.isspace() for character in token)
    ):
        raise AuthenticationError("Authentication required")
    return token


def get_cognito_token_verifier() -> CognitoTokenVerifier:
    """FastAPI-overridable dependency for onboarding's separately supplied ID token.

    The protected Core API continues to obtain an ``ActorContext`` through
    ``get_authenticator`` and Cognito *access* tokens.  An onboarding handler
    may instead depend on this verifier and call ``verify_id_token``; it gets
    only a verified subject/email and still cannot mint a role or tenant.
    """
    settings = get_settings()
    if getattr(settings, "cognito_auth_enabled", False) is not True:
        raise NoAuthenticatorConfiguredError("Cognito authentication is not enabled")
    return _get_cognito_token_verifier_from_settings(settings)


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


@lru_cache(maxsize=16)
def _build_cognito_token_verifier(
    region: str,
    user_pool_id: str,
    app_client_id: str,
    jwks_cache_seconds: int,
    http_timeout_seconds: float,
) -> CognitoTokenVerifier:
    """Keep one JWKS cache per immutable Cognito configuration in this process."""
    from app.adapters.auth.cognito import CognitoJwtVerifier

    return CognitoJwtVerifier(
        region=region,
        user_pool_id=user_pool_id,
        app_client_id=app_client_id,
        jwks_cache_seconds=jwks_cache_seconds,
        http_timeout_seconds=http_timeout_seconds,
    )


def _get_cognito_token_verifier_from_settings(settings) -> CognitoTokenVerifier:
    return _build_cognito_token_verifier(
        settings.cognito_region,
        settings.cognito_user_pool_id,
        settings.cognito_app_client_id,
        settings.cognito_jwks_cache_seconds,
        settings.cognito_http_timeout_seconds,
    )


async def get_actor_context(
    request: Request,
    authenticator: Authenticator = Depends(get_authenticator),
) -> ActorContext:
    """FastAPI dependency for protected routes.

    Calls the authenticator to resolve the actor's identity. On failure,
    raises AuthenticationError which maps to HTTP 401.
    """
    try:
        return await authenticator.authenticate(request)
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError("Authentication failed") from exc
