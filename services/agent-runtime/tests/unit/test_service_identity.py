"""Request-bound service identity must fail closed at every trust check."""

from __future__ import annotations

import pytest

from agent_runtime.common.errors import ServiceAuthenticationError
from agent_runtime.security.service_identity import (
    ServiceCredentialSigner,
    ServiceCredentialVerifier,
)

SECRET = "synthetic-test-service-identity-secret-32-bytes"
BODY = b'{"synthetic":true}'
NOW = 1_786_590_000


def signer(**overrides: object) -> ServiceCredentialSigner:
    return ServiceCredentialSigner(secret=SECRET, **overrides)


def verifier() -> ServiceCredentialVerifier:
    return ServiceCredentialVerifier(
        secret=SECRET,
        issuer="kinsun-local",
        expected_subject="core-api",
        audience="agent-runtime",
        max_ttl_seconds=60,
    )


def token(**overrides: object) -> str:
    values = {
        "method": "POST",
        "path": "/api/v1/agent/runs",
        "body": BODY,
        "correlation_id": "cid-001",
        "issued_at": NOW,
        "credential_id": "credential-001",
    }
    values.update(overrides)
    return signer().sign(**values)  # type: ignore[arg-type]


def verify(service_token: str | None, **overrides: object):
    values = {
        "method": "POST",
        "path": "/api/v1/agent/runs",
        "body": BODY,
        "correlation_id": "cid-001",
        "now": NOW,
    }
    values.update(overrides)
    return verifier().verify(service_token, **values)  # type: ignore[arg-type]


def test_valid_credential_resolves_only_the_core_service_principal() -> None:
    principal = verify(token())
    assert principal.subject == "core-api"
    assert principal.audience == "agent-runtime"


@pytest.mark.parametrize(
    ("service_token", "verify_overrides"),
    [
        (None, {}),
        ("browser-bearer-token", {}),
        (token(), {"body": b'{"synthetic":false}'}),
        (token(), {"path": "/api/v1/rag/retrievals"}),
        (token(), {"method": "GET"}),
        (token(), {"correlation_id": "cid-other"}),
        (token(issued_at=NOW - 31), {"now": NOW + 1}),
    ],
)
def test_invalid_request_binding_is_rejected(
    service_token: str | None,
    verify_overrides: dict[str, object],
) -> None:
    with pytest.raises(ServiceAuthenticationError):
        verify(service_token, **verify_overrides)


def test_wrong_audience_is_rejected() -> None:
    wrong = ServiceCredentialSigner(
        secret=SECRET,
        audience="core-api",
    ).sign(
        method="POST",
        path="/api/v1/agent/runs",
        body=BODY,
        correlation_id="cid-001",
        issued_at=NOW,
        credential_id="credential-wrong-audience",
    )
    with pytest.raises(ServiceAuthenticationError):
        verify(wrong)


def test_replay_is_rejected() -> None:
    service_token = token(credential_id="credential-replay")
    replay_verifier = verifier()
    request = {
        "method": "POST",
        "path": "/api/v1/agent/runs",
        "body": BODY,
        "correlation_id": "cid-001",
        "now": NOW,
    }
    replay_verifier.verify(service_token, **request)
    with pytest.raises(ServiceAuthenticationError):
        replay_verifier.verify(service_token, **request)
