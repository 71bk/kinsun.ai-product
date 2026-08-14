from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.kinsun_identity import KinsunEmailChallenge
from app.services.kinsun_email_auth_service import (
    KinsunEmailAuthService,
    KinsunEmailChallengePolicy,
    RejectedKinsunEmailAuthentication,
)
from app.services.kinsun_identity_codec import (
    KinsunEmailChallengeCodec,
    KinsunIdentityCodec,
)

_NOW = datetime(2026, 8, 14, 17, 0, tzinfo=UTC)
_IDENTITY_CODEC = KinsunIdentityCodec(
    "kinsun-email-service-identity-secret-material-32-bytes",
    1,
)
_CHALLENGE_CODEC = KinsunEmailChallengeCodec(
    "kinsun-email-service-challenge-secret-material-32-bytes"
)


class _Repository:
    def __init__(self) -> None:
        self.pending: KinsunEmailChallenge | None = None
        self.added: list[KinsunEmailChallenge] = []
        self.flush_count = 0

    async def acquire_subject_lock(self, *, subject_digest: str, key_version: int) -> None:
        del subject_digest, key_version

    async def get_pending_by_subject(self, **kwargs):
        del kwargs
        return self.pending

    async def get_by_token_digest(self, token_digest: str, *, for_update: bool = False):
        del token_digest, for_update
        return self.pending

    async def list_identities_by_subject(self, **kwargs):
        del kwargs
        return []

    def add_challenge(self, challenge: KinsunEmailChallenge) -> None:
        self.pending = challenge
        self.added.append(challenge)

    async def flush(self) -> None:
        self.flush_count += 1


class _Unused:
    pass


def _service(repository: _Repository) -> KinsunEmailAuthService:
    return KinsunEmailAuthService(
        _Unused(),  # type: ignore[arg-type]
        identity_codec=_IDENTITY_CODEC,
        challenge_codec=_CHALLENGE_CODEC,
        app_session_service=_Unused(),  # type: ignore[arg-type]
        family_invitation_service=_Unused(),  # type: ignore[arg-type]
        password_auth_service=_Unused(),  # type: ignore[arg-type]
        policy=KinsunEmailChallengePolicy(ttl=timedelta(minutes=10), max_attempts=3),
        verification_code="246810",
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )


@pytest.mark.asyncio
async def test_start_normalizes_email_and_never_exposes_code() -> None:
    repository = _Repository()

    result = await _service(repository).start(
        email=" Person@Example.COM ",
        intent="ELDER",
        display_name=" 王阿姨 ",
    )

    challenge = repository.added[0]
    assert result.token.startswith("ke1_")
    assert not hasattr(result, "verification_code")
    assert challenge.email_address == "person@example.com"
    assert challenge.display_name == "王阿姨"
    assert challenge.code_digest != "246810"
    assert challenge.attempt_count == 0


@pytest.mark.asyncio
async def test_wrong_code_increments_attempt_and_locks_at_limit() -> None:
    repository = _Repository()
    service = _service(repository)
    started = await service.start(
        email="person@example.com",
        intent="ELDER",
        display_name=None,
    )
    assert repository.pending is not None
    repository.pending.attempt_count = 2

    result = await service.complete(
        challenge_token=started.token,
        verification_code="000000",
        password="a-valid-demo-password",
        invitation_code=None,
        trace_id="trace",
        idempotency_key="operation",
    )

    assert isinstance(result, RejectedKinsunEmailAuthentication)
    assert repository.pending.attempt_count == 3
    assert repository.pending.status == "LOCKED"
    assert repository.pending.invalidated_at == _NOW
