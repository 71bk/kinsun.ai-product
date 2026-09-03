from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.core.exceptions import SpeechSynthesisRateLimitError
from app.repositories.speech_synthesis_claim_repo import (
    SpeechSynthesisClaimRepository,
    SpeechSynthesisQuota,
)

TENANT_ID = UUID("53000000-0000-4000-8000-000000000001")
ACTOR_ID = UUID("54000000-0000-4000-8000-000000000001")
SESSION_ID = UUID("51000000-0000-4000-8000-000000000001")
AGENT_RUN_ID = UUID("52000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 9, 3, 2, 0, tzinfo=UTC)


def _quota(**overrides: int) -> SpeechSynthesisQuota:
    values = {
        "window_seconds": 60,
        "client_requests": 30,
        "client_characters": 30_000,
        "actor_requests": 20,
        "actor_characters": 20_000,
        "tenant_requests": 100,
        "tenant_characters": 100_000,
        **overrides,
    }
    return SpeechSynthesisQuota(**values)


def _claim_args(quota: SpeechSynthesisQuota) -> dict[str, object]:
    return {
        "capability_digest": "a" * 64,
        "tenant_id": TENANT_ID,
        "actor_id": ACTOR_ID,
        "session_id": SESSION_ID,
        "agent_run_id": AGENT_RUN_ID,
        "client_ip_hash": "b" * 64,
        "character_count": 12,
        "expires_at": NOW + timedelta(seconds=60),
        "quota": quota,
        "now": NOW,
    }


@pytest.mark.asyncio
async def test_claim_locks_all_scopes_before_usage_checks_and_insert() -> None:
    session = AsyncMock()
    session.scalar.side_effect = [None, "a" * 64]
    usage_result = SimpleNamespace(
        one=lambda: SimpleNamespace(
            request_count=0,
            character_count=0,
        )
    )
    session.execute.return_value = usage_result

    await SpeechSynthesisClaimRepository(session).claim(**_claim_args(_quota()))

    lock_calls = [
        call for call in session.execute.await_args_list if "advisory" in str(call.args[0])
    ]
    usage_calls = [
        call for call in session.execute.await_args_list if "count(*)" in str(call.args[0])
    ]
    assert len(lock_calls) == 3
    assert len(usage_calls) == 3
    assert session.scalar.await_count == 2


@pytest.mark.asyncio
async def test_quota_denial_is_atomic_and_reports_window_retry_after() -> None:
    session = AsyncMock()
    session.scalar.return_value = None
    usage_result = SimpleNamespace(
        one=lambda: SimpleNamespace(
            request_count=1,
            character_count=12,
        )
    )
    session.execute.return_value = usage_result

    with pytest.raises(SpeechSynthesisRateLimitError) as caught:
        await SpeechSynthesisClaimRepository(session).claim(**_claim_args(_quota(actor_requests=1)))

    assert caught.value.retry_after_seconds == 60
    assert session.scalar.await_count == 1
