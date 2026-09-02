"""Request-bound service identity must fail closed at every trust check."""

from __future__ import annotations

import pytest

from agent_runtime.common.errors import ServiceAuthenticationError
from agent_runtime.security.replay_store import (
    InMemoryReplayStore,
    ReplayStore,
    ReplayStoreError,
)
from agent_runtime.security.service_identity import (
    ServiceCredentialSigner,
    ServiceCredentialVerifier,
)

SECRET = "synthetic-test-service-identity-secret-32-bytes"
BODY = b'{"synthetic":true}'
NOW = 1_786_590_000


def signer(**overrides: object) -> ServiceCredentialSigner:
    return ServiceCredentialSigner(secret=SECRET, **overrides)


def verifier(replay_store: ReplayStore | None = None) -> ServiceCredentialVerifier:
    return ServiceCredentialVerifier(
        secret=SECRET,
        issuer="kinsun-local",
        expected_subject="core-api",
        audience="agent-runtime",
        replay_store=replay_store or InMemoryReplayStore(),
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


async def verify(service_token: str | None, **overrides: object):
    values = {
        "method": "POST",
        "path": "/api/v1/agent/runs",
        "body": BODY,
        "correlation_id": "cid-001",
        "now": NOW,
    }
    values.update(overrides)
    return await verifier().verify(service_token, **values)  # type: ignore[arg-type]


async def test_valid_credential_resolves_only_the_core_service_principal() -> None:
    principal = await verify(token())
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
async def test_invalid_request_binding_is_rejected(
    service_token: str | None,
    verify_overrides: dict[str, object],
) -> None:
    with pytest.raises(ServiceAuthenticationError):
        await verify(service_token, **verify_overrides)


async def test_wrong_audience_is_rejected() -> None:
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
        await verify(wrong)


async def test_replay_is_rejected() -> None:
    service_token = token(credential_id="credential-replay")
    replay_verifier = verifier()
    request = {
        "method": "POST",
        "path": "/api/v1/agent/runs",
        "body": BODY,
        "correlation_id": "cid-001",
        "now": NOW,
    }
    await replay_verifier.verify(service_token, **request)
    with pytest.raises(ServiceAuthenticationError):
        await replay_verifier.verify(service_token, **request)


async def test_second_replica_sharing_the_store_rejects_the_replay() -> None:
    """Two verifiers stand in for two replicas of the same audience."""

    shared_store = InMemoryReplayStore()
    service_token = token(credential_id="credential-multi-replica")
    request = {
        "method": "POST",
        "path": "/api/v1/agent/runs",
        "body": BODY,
        "correlation_id": "cid-001",
        "now": NOW,
    }

    await verifier(shared_store).verify(service_token, **request)

    with pytest.raises(ServiceAuthenticationError):
        await verifier(shared_store).verify(service_token, **request)


async def test_verifier_requires_an_explicit_replay_store() -> None:
    with pytest.raises(TypeError):
        ServiceCredentialVerifier(  # type: ignore[call-arg]
            secret=SECRET,
            issuer="kinsun-local",
            expected_subject="core-api",
            audience="agent-runtime",
        )


async def test_undecidable_claim_is_rejected_rather_than_accepted() -> None:
    class _FailingStore:
        durable = True

        async def claim(self, **_: object) -> bool:
            raise ReplayStoreError("replay claim failed: SyntheticError")

        async def aclose(self) -> None:
            return None

    service_token = token(credential_id="credential-store-failure")

    with pytest.raises(ServiceAuthenticationError):
        await verifier(_FailingStore()).verify(
            service_token,
            method="POST",
            path="/api/v1/agent/runs",
            body=BODY,
            correlation_id="cid-001",
            now=NOW,
        )
