"""Verify cross-replica service credential replay rejection against a database.

Two verifiers with independent sessions stand in for two replicas of the same
audience. The second one must reject a credential the first already claimed,
and a concurrent pair must admit exactly one.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_API_ROOT = REPO_ROOT / "services" / "core-api"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(CORE_API_ROOT))

from app.adapters.service_identity import (  # noqa: E402
    ServiceCredentialSigner,
    ServiceCredentialVerifier,
)
from app.adapters.service_identity_replay_db import DatabaseReplayStore  # noqa: E402
from app.core.exceptions import AuthenticationError  # noqa: E402
from scripts.seed_demo import _database_url  # noqa: E402

# Synthetic, verifier-local material. It is never a configured runtime secret.
_SECRET = "synthetic-verifier-service-identity-secret-32-bytes"
_ISSUER = "kinsun-qa-replay"
_PATH = "/api/v1/internal/voice-tickets/consume"
_BODY = b'{"session_id":"synthetic-replay-verifier"}'


def _signer() -> ServiceCredentialSigner:
    return ServiceCredentialSigner(
        secret=_SECRET,
        issuer=_ISSUER,
        subject="speech-gateway",
        audience="core-api",
        ttl_seconds=30,
    )


def _replica(engine) -> ServiceCredentialVerifier:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return ServiceCredentialVerifier(
        secret=_SECRET,
        issuer=_ISSUER,
        expected_subject="speech-gateway",
        audience="core-api",
        replay_store=DatabaseReplayStore(lambda: factory),
        max_ttl_seconds=30,
    )


async def main() -> None:
    engine = create_async_engine(_database_url(), hide_parameters=True)
    sequential_id = str(uuid4())
    concurrent_id = str(uuid4())
    correlation_id = f"qa-replay-{uuid4()}"
    request = {
        "method": "POST",
        "path": _PATH,
        "body": _BODY,
        "correlation_id": correlation_id,
    }

    try:
        sequential_token = _signer().sign(credential_id=sequential_id, **request)
        await _replica(engine).verify(sequential_token, **request)
        sequential_replay_rejected = False
        try:
            await _replica(engine).verify(sequential_token, **request)
        except AuthenticationError:
            sequential_replay_rejected = True

        concurrent_token = _signer().sign(credential_id=concurrent_id, **request)
        results = await asyncio.gather(
            _replica(engine).verify(concurrent_token, **request),
            _replica(engine).verify(concurrent_token, **request),
            return_exceptions=True,
        )
        accepted = sum(1 for result in results if not isinstance(result, BaseException))
        rejected = sum(1 for result in results if isinstance(result, AuthenticationError))

        if not sequential_replay_rejected or accepted != 1 or rejected != 1:
            raise RuntimeError("Cross-replica replay verification failed")
        print(
            json.dumps(
                {
                    "ok": True,
                    "sequential_replay_rejected": sequential_replay_rejected,
                    "concurrent_accepted": accepted,
                    "concurrent_rejected": rejected,
                }
            )
        )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM service_identity.credential_nonce WHERE issuer = :issuer"),
                {"issuer": _ISSUER},
            )
            remaining = await connection.scalar(
                text(
                    "SELECT count(*) FROM service_identity.credential_nonce "
                    "WHERE issuer = :issuer"
                ),
                {"issuer": _ISSUER},
            )
        if remaining:
            raise RuntimeError("Verifier cleanup failed")
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
