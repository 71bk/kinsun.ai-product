"""Database-backed authenticator for Core-owned opaque App Sessions."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ServiceUnavailableError
from app.db.engine import DatabaseEngine
from app.middleware.auth import ActorContext, Authenticator
from app.services.app_session_service import AppSessionPolicy, AppSessionService

_AUTHENTICATION_REQUIRED = "Authentication required"


class DatabaseAppSessionAuthenticator(Authenticator):
    """Resolve one opaque bearer credential against live Core state.

    Authentication owns a short database transaction because the auth
    dependency runs before an endpoint's request-scoped database dependency.
    Successful authentication may touch ``last_seen_at``; rejected credentials
    are rolled back and never appear in logs or error details.
    """

    def __init__(self, db_engine: DatabaseEngine, settings: Settings) -> None:
        self._db_engine = db_engine
        self._policy = AppSessionPolicy.from_settings(settings)

    async def authenticate(self, request: Request) -> ActorContext:
        token = _extract_bearer_token(request)
        if not token.startswith("ks1_"):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        if not self._db_engine.is_ready:
            try:
                recovered = await self._db_engine.recover_connectivity()
            except Exception:
                recovered = False
            if not recovered:
                raise ServiceUnavailableError("Authentication service is unavailable")

        async with self._db_engine.session_factory() as session:
            try:
                actor = await AppSessionService(session, self._policy).authenticate(token)
                await session.commit()
                return actor
            except AuthenticationError:
                await session.rollback()
                raise
            except DBAPIError as exc:
                await session.rollback()
                if exc.connection_invalidated:
                    self._db_engine.mark_unready()
                raise ServiceUnavailableError("Authentication service is unavailable") from None
            except SQLAlchemyError:
                await session.rollback()
                raise ServiceUnavailableError("Authentication service is unavailable") from None
            except Exception:
                await session.rollback()
                raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None


def _extract_bearer_token(request: Request) -> str:
    values = request.headers.getlist("authorization")
    if len(values) != 1:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    scheme, separator, token = values[0].partition(" ")
    if (
        separator != " "
        or scheme.casefold() != "bearer"
        or not token
        or len(token) > 128
        or any(character.isspace() for character in token)
    ):
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    return token
