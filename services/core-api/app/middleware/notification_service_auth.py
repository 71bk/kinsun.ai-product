"""Local/test scheduler credentials; scope always comes from live Core state."""

from functools import lru_cache

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.service_identity import SERVICE_CREDENTIAL_HEADER, ServiceCredentialVerifier
from app.adapters.service_identity_replay_db import DatabaseReplayStore
from app.core.auth import ActorContext
from app.core.config import AppEnv, get_settings
from app.core.correlation import get_correlation_id
from app.core.exceptions import AuthenticationError, ServiceUnavailableError
from app.db.session import get_db_engine
from app.middleware.logging import bind_request_actor_context
from app.repositories.notification_service_actor_repo import get_notification_service_actor
from app.services.actor_context_resolver import resolve_active_actor_context


@lru_cache(maxsize=1)
def get_notification_service_verifier() -> ServiceCredentialVerifier:
    settings = get_settings()
    if not settings.notification_worker_identity_enabled or settings.app_env == AppEnv.PRODUCTION:
        raise ServiceUnavailableError("Notification service identity is unavailable")
    store = DatabaseReplayStore(lambda: get_db_engine().session_factory)
    if not store.durable:  # pragma: no cover
        raise ServiceUnavailableError("Notification service identity is unavailable")
    try:
        return ServiceCredentialVerifier(
            secret=settings.notification_worker_hmac_secret,
            issuer=settings.notification_worker_issuer,
            expected_subject="notification-worker",
            audience="core-api",
            max_ttl_seconds=30,
            replay_store=store,
        )
    except ValueError:
        raise ServiceUnavailableError("Notification service identity is unavailable") from None


async def resolve_notification_actor() -> ActorContext:
    settings = get_settings()
    engine = get_db_engine()
    if not engine.is_ready or settings.notification_worker_actor_id is None:
        raise ServiceUnavailableError("Notification service identity is unavailable")
    try:
        async with engine.session_factory() as session:
            actor = await get_notification_service_actor(
                session, settings.notification_worker_actor_id
            )
            if actor is None:
                raise AuthenticationError("Authentication required")
            return await resolve_active_actor_context(session, actor)
    except SQLAlchemyError:
        raise ServiceUnavailableError("Notification service identity is unavailable") from None


async def require_notification_service_actor(request: Request) -> ActorContext:
    values = request.headers.getlist(SERVICE_CREDENTIAL_HEADER)
    # No browser App Session, cookie, query credential, or fake-role fallback.
    if len(values) != 1 or not values[0] or request.headers.get("authorization"):
        raise AuthenticationError("Authentication required")
    try:
        await get_notification_service_verifier().verify(
            values[0],
            method=request.method,
            path=request.url.path,
            body=await request.body(),
            correlation_id=get_correlation_id(),
        )
    except SQLAlchemyError:
        raise ServiceUnavailableError("Notification service identity is unavailable") from None
    actor = await resolve_notification_actor()
    if actor.actor_role != "SYSTEM_SERVICE" or actor.status != "ACTIVE":
        raise AuthenticationError("Authentication required")
    bind_request_actor_context(request, actor_id=actor.actor_id, tenant_id=actor.tenant_id)
    return actor
