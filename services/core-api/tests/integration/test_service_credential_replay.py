"""PostgreSQL proof that a replayed credential cannot cross replicas."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapters.service_identity import ServiceCredentialSigner, ServiceCredentialVerifier
from app.adapters.service_identity_replay_db import DatabaseReplayStore
from app.core.exceptions import AuthenticationError

_SECRET = "synthetic-service-identity-secret-material-32-bytes"
_BODY = b'{"session_id":"synthetic-replay"}'
_PATH = "/api/v1/internal/voice-tickets/consume"


def _signer() -> ServiceCredentialSigner:
    return ServiceCredentialSigner(
        secret=_SECRET,
        issuer="kinsun-test",
        subject="speech-gateway",
        audience="core-api",
        ttl_seconds=30,
    )


def _replica(test_engine) -> ServiceCredentialVerifier:
    """One verifier with its own sessions, standing in for a separate replica."""

    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    return ServiceCredentialVerifier(
        secret=_SECRET,
        issuer="kinsun-test",
        expected_subject="speech-gateway",
        audience="core-api",
        replay_store=DatabaseReplayStore(lambda: factory),
        max_ttl_seconds=30,
    )


async def _clear_nonces(test_engine) -> None:
    async with test_engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM service_identity.credential_nonce "
                "WHERE issuer = 'kinsun-test' OR credential_id LIKE 'a3000000-%'"
            )
        )


@pytest.mark.asyncio
async def test_second_replica_rejects_a_credential_the_first_already_claimed(
    test_engine,
) -> None:
    await _clear_nonces(test_engine)
    credential_id = "a3000000-0000-4000-8000-000000000001"
    token = _signer().sign(
        method="POST",
        path=_PATH,
        body=_BODY,
        correlation_id="correlation-replay-1",
        credential_id=credential_id,
    )
    request = {
        "method": "POST",
        "path": _PATH,
        "body": _BODY,
        "correlation_id": "correlation-replay-1",
    }

    try:
        principal = await _replica(test_engine).verify(token, **request)
        assert principal.credential_id == credential_id

        with pytest.raises(AuthenticationError):
            await _replica(test_engine).verify(token, **request)

        async with test_engine.begin() as conn:
            claimed = await conn.scalar(
                text(
                    "SELECT count(*) FROM service_identity.credential_nonce "
                    "WHERE audience = 'core-api' AND credential_id = :credential_id"
                ),
                {"credential_id": credential_id},
            )
        assert claimed == 1
    finally:
        await _clear_nonces(test_engine)


@pytest.mark.asyncio
async def test_concurrent_replicas_admit_exactly_one_claim(test_engine) -> None:
    await _clear_nonces(test_engine)
    credential_id = "a3000000-0000-4000-8000-000000000002"
    token = _signer().sign(
        method="POST",
        path=_PATH,
        body=_BODY,
        correlation_id="correlation-replay-2",
        credential_id=credential_id,
    )
    request = {
        "method": "POST",
        "path": _PATH,
        "body": _BODY,
        "correlation_id": "correlation-replay-2",
    }

    try:
        results = await asyncio.gather(
            _replica(test_engine).verify(token, **request),
            _replica(test_engine).verify(token, **request),
            return_exceptions=True,
        )

        accepted = [result for result in results if not isinstance(result, BaseException)]
        rejected = [result for result in results if isinstance(result, AuthenticationError)]
        assert len(accepted) == 1
        assert len(rejected) == 1
    finally:
        await _clear_nonces(test_engine)


@pytest.mark.asyncio
async def test_expired_rows_are_purged_without_freeing_a_live_claim(test_engine) -> None:
    await _clear_nonces(test_engine)
    credential_id = "a3000000-0000-4000-8000-000000000003"
    token = _signer().sign(
        method="POST",
        path=_PATH,
        body=_BODY,
        correlation_id="correlation-replay-3",
        credential_id=credential_id,
    )

    try:
        async with test_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO service_identity.credential_nonce "
                    "(audience, credential_id, issuer, subject, expires_at) "
                    "VALUES ('core-api', 'a3000000-0000-4000-8000-000000000099', "
                    "'kinsun-test', 'speech-gateway', now() - interval '5 minutes')"
                )
            )

        await _replica(test_engine).verify(
            token,
            method="POST",
            path=_PATH,
            body=_BODY,
            correlation_id="correlation-replay-3",
        )

        async with test_engine.begin() as conn:
            remaining = [
                row.credential_id
                for row in (
                    await conn.execute(
                        text(
                            "SELECT credential_id FROM service_identity.credential_nonce "
                            "WHERE issuer = 'kinsun-test' ORDER BY credential_id"
                        )
                    )
                )
            ]

        assert remaining == [credential_id]
    finally:
        await _clear_nonces(test_engine)
