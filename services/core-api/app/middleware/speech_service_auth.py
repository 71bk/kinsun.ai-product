"""Request-bound authentication for Speech Gateway private Core calls."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Request

from app.adapters.service_identity import (
    SERVICE_CREDENTIAL_HEADER,
    ServiceCredentialVerifier,
    ServicePrincipal,
)
from app.core.config import get_settings
from app.core.correlation import get_correlation_id
from app.core.exceptions import ServiceUnavailableError


@lru_cache(maxsize=1)
def get_speech_service_verifier() -> ServiceCredentialVerifier:
    settings = get_settings()
    if not settings.speech_service_identity_enabled:
        raise ServiceUnavailableError("Speech service identity is not configured")
    try:
        return ServiceCredentialVerifier(
            secret=settings.speech_service_identity_hmac_secret,
            issuer=settings.speech_service_identity_issuer,
            expected_subject="speech-gateway",
            audience="core-api",
            max_ttl_seconds=settings.speech_service_identity_ttl_seconds,
        )
    except ValueError:
        raise ServiceUnavailableError("Speech service identity is not configured") from None


async def require_speech_service(
    request: Request,
    verifier: ServiceCredentialVerifier = Depends(get_speech_service_verifier),
) -> ServicePrincipal:
    """Authenticate Speech Gateway without issuing a browser App Session."""
    return verifier.verify(
        request.headers.get(SERVICE_CREDENTIAL_HEADER),
        method=request.method,
        path=request.url.path,
        body=await request.body(),
        correlation_id=get_correlation_id(),
    )
