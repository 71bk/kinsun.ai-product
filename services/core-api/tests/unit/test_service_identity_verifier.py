"""Request-bound Speech-to-Core service identity tests."""

from __future__ import annotations

import pytest

from app.adapters.service_identity import ServiceCredentialSigner, ServiceCredentialVerifier
from app.adapters.service_identity_replay import InMemoryReplayStore, ReplayStore
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


def _verifier(replay_store: ReplayStore | None = None) -> ServiceCredentialVerifier:
    return ServiceCredentialVerifier(
        secret=_SECRET,
        issuer="kinsun-test",
        expected_subject="speech-gateway",
        audience="core-api",
        replay_store=replay_store or InMemoryReplayStore(),
        max_ttl_seconds=30,
    )


async def test_request_bound_speech_credential_is_accepted_once() -> None:
    token = _signer().sign(
        method="POST",
        path="/api/v1/internal/voice-tickets/consume",
        body=_BODY,
        correlation_id="correlation-1",
        issued_at=100,
        credential_id="00000000-0000-4000-8000-000000000001",
    )
    verifier = _verifier()

    principal = await verifier.verify(
        token,
        method="POST",
        path="/api/v1/internal/voice-tickets/consume",
        body=_BODY,
        correlation_id="correlation-1",
        now=101,
    )

    assert principal.subject == "speech-gateway"
    with pytest.raises(AuthenticationError):
        await verifier.verify(
            token,
            method="POST",
            path="/api/v1/internal/voice-tickets/consume",
            body=_BODY,
            correlation_id="correlation-1",
            now=101,
        )


async def test_second_replica_sharing_the_store_rejects_the_replay() -> None:
    """Two verifiers stand in for two replicas of the same audience."""

    shared_store = InMemoryReplayStore()
    token = _signer().sign(
        method="POST",
        path="/api/v1/internal/voice-tickets/consume",
        body=_BODY,
        correlation_id="correlation-1",
        issued_at=100,
        credential_id="00000000-0000-4000-8000-000000000002",
    )
    request = {
        "method": "POST",
        "path": "/api/v1/internal/voice-tickets/consume",
        "body": _BODY,
        "correlation_id": "correlation-1",
        "now": 101,
    }

    await _verifier(shared_store).verify(token, **request)

    with pytest.raises(AuthenticationError):
        await _verifier(shared_store).verify(token, **request)


async def test_verifier_requires_an_explicit_replay_store() -> None:
    with pytest.raises(TypeError):
        ServiceCredentialVerifier(  # type: ignore[call-arg]
            secret=_SECRET,
            issuer="kinsun-test",
            expected_subject="speech-gateway",
            audience="core-api",
        )


@pytest.mark.parametrize(
    ("path", "body", "correlation_id"),
    [
        ("/api/v1/internal/asr-results", _BODY, "correlation-1"),
        ("/api/v1/internal/voice-tickets/consume", b"{}", "correlation-1"),
        ("/api/v1/internal/voice-tickets/consume", _BODY, "correlation-2"),
    ],
)
async def test_request_binding_mismatch_is_rejected(
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
        await _verifier().verify(
            token,
            method="POST",
            path=path,
            body=body,
            correlation_id=correlation_id,
            now=101,
        )
