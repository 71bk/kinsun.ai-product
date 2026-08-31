"""Request-bound Speech-to-Core service identity tests."""

from __future__ import annotations

import pytest

from app.adapters.service_identity import ServiceCredentialSigner, ServiceCredentialVerifier
from app.core.exceptions import AuthenticationError

_SECRET = "synthetic-service-identity-secret-material-32-bytes"
_BODY = b'{"session_id":"synthetic"}'


def _signer() -> ServiceCredentialSigner:
    return ServiceCredentialSigner(
        secret=_SECRET,
        issuer="kinsun-test",
        subject="speech-gateway",
        audience="core-api",
        ttl_seconds=30,
    )


def _verifier() -> ServiceCredentialVerifier:
    return ServiceCredentialVerifier(
        secret=_SECRET,
        issuer="kinsun-test",
        expected_subject="speech-gateway",
        audience="core-api",
        max_ttl_seconds=30,
    )


def test_request_bound_speech_credential_is_accepted_once() -> None:
    token = _signer().sign(
        method="POST",
        path="/api/v1/internal/voice-tickets/consume",
        body=_BODY,
        correlation_id="correlation-1",
        issued_at=100,
        credential_id="00000000-0000-4000-8000-000000000001",
    )
    verifier = _verifier()

    principal = verifier.verify(
        token,
        method="POST",
        path="/api/v1/internal/voice-tickets/consume",
        body=_BODY,
        correlation_id="correlation-1",
        now=101,
    )

    assert principal.subject == "speech-gateway"
    with pytest.raises(AuthenticationError):
        verifier.verify(
            token,
            method="POST",
            path="/api/v1/internal/voice-tickets/consume",
            body=_BODY,
            correlation_id="correlation-1",
            now=101,
        )


@pytest.mark.parametrize(
    ("path", "body", "correlation_id"),
    [
        ("/api/v1/internal/asr-results", _BODY, "correlation-1"),
        ("/api/v1/internal/voice-tickets/consume", b"{}", "correlation-1"),
        ("/api/v1/internal/voice-tickets/consume", _BODY, "correlation-2"),
    ],
)
def test_request_binding_mismatch_is_rejected(
    path: str,
    body: bytes,
    correlation_id: str,
) -> None:
    token = _signer().sign(
        method="POST",
        path="/api/v1/internal/voice-tickets/consume",
        body=_BODY,
        correlation_id="correlation-1",
        issued_at=100,
    )

    with pytest.raises(AuthenticationError):
        _verifier().verify(
            token,
            method="POST",
            path=path,
            body=body,
            correlation_id=correlation_id,
            now=101,
        )
