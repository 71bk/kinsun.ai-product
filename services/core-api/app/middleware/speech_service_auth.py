"""Request-bound authentication for Speech Gateway private Core calls."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request

from app.adapters.service_identity import (
    SERVICE_CREDENTIAL_HEADER,
    ServiceCredentialVerifier,
    ServicePrincipal,
)
from app.adapters.service_identity_replay_db import DatabaseReplayStore
from app.core.config import get_settings
from app.core.correlation import get_correlation_id
from app.core.exceptions import ServiceUnavailableError
from app.db.session import get_db_engine


@lru_cache(maxsize=1)
def get_speech_service_verifier() -> ServiceCredentialVerifier:
    settings = get_settings()
    if not settings.speech_service_identity_enabled:
        raise ServiceUnavailableError("Speech service identity is not configured")
    replay_store = DatabaseReplayStore(lambda: get_db_engine().session_factory)
    if not replay_store.durable:  # pragma: no cover - guards a future wiring mistake
        raise ServiceUnavailableError("Speech service identity is not configured")
    try:
        return ServiceCredentialVerifier(
            secret=settings.speech_service_identity_hmac_secret,
            issuer=settings.speech_service_identity_issuer,
            expected_subject="speech-gateway",
            audience="core-api",
            replay_store=replay_store,
            max_ttl_seconds=settings.speech_service_identity_ttl_seconds,
        )
    except ValueError:
        raise ServiceUnavailableError("Speech service identity is not configured") from None


async def require_speech_service(
    request: Request,
    verifier: ServiceCredentialVerifier = Depends(get_speech_service_verifier),
) -> ServicePrincipal:
    """Authenticate Speech Gateway without issuing a browser App Session."""
    return await verifier.verify(
        request.headers.get(SERVICE_CREDENTIAL_HEADER),
        method=request.method,
        path=request.url.path,
        body=await request.body(),
        correlation_id=get_correlation_id(),
    )
