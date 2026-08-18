"""Deterministic DecisionSupportProfile resolution and Memory policy tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.policies.decision_support import (
    DecisionSupportResolution,
    apply_decision_support_profile,
    profile_binding_is_current,
)
from app.policies.memory_policy import (
    CURRENT_MEMORY_POLICY_VERSION,
    MemoryCandidatePolicyDecision,
)
from app.repositories.decision_support_repo import DecisionSupportProfileRepository


def _low_decision() -> MemoryCandidatePolicyDecision:
    return MemoryCandidatePolicyDecision(
        create_memory=True,
        status="ACTIVE",
        actual_risk_level="LOW",
        policy_decision="AUTO_ACTIVATED_LOW",
        verification_level="POLICY_VERIFIED",
        required_verification="NONE",
        reason_code="LOW_ALL_OF_SATISFIED",
    )


def _profile(
    *,
    data_class: str,
    mode: str = "SUPPORTED",
    profile_version: int = 1,
    effective_from: datetime,
    expires_at: datetime | None,
    allowed_memory_risks: list[str] | None = None,
    policy_version: str = CURRENT_MEMORY_POLICY_VERSION,
) -> SimpleNamespace:
    return SimpleNamespace(
        decision_support_profile_id=uuid4(),
        data_class=data_class,
        mode=mode,
        profile_version=profile_version,
        effective_from=effective_from,
        expires_at=expires_at,
        allowed_memory_risks=(
            allowed_memory_risks if allowed_memory_risks is not None else ["LOW", "MEDIUM"]
        ),
        basis_reference="restricted-care-record:opaque-reference",
        policy_version=policy_version,
    )


@pytest.mark.asyncio
async def test_no_authored_profile_preserves_default_standard_policy() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    elder_id = uuid4()
    tenant_id = uuid4()

    resolution = await DecisionSupportProfileRepository(
        session,
        tenant_id,
    ).resolve_for_memory(elder_id=elder_id, data_class="PREFERENCE")

    assert resolution.is_default_standard is True
    assert resolution.profile_id is None
    statement = session.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
    assert "decision_support_profile.tenant_id" in compiled
    assert "decision_support_profile.elder_id" in compiled
    assert "decision_support_profile.decision_scope" in compiled


@pytest.mark.asyncio
async def test_exact_active_profile_wins_over_all_memory_profile() -> None:
    now = datetime.now(UTC)
    general = _profile(
        data_class="ALL_MEMORY",
        mode="STANDARD",
        effective_from=now - timedelta(days=2),
        expires_at=None,
    )
    exact = _profile(
        data_class="PREFERENCE",
        profile_version=2,
        effective_from=now - timedelta(days=1),
        expires_at=now + timedelta(days=1),
    )
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [general, exact]
    session.execute.return_value = result

    resolution = await DecisionSupportProfileRepository(
        session,
        uuid4(),
    ).resolve_for_memory(elder_id=uuid4(), data_class="PREFERENCE", at=now)

    assert resolution.usable is True
    assert resolution.mode == "SUPPORTED"
    assert resolution.profile_id == exact.decision_support_profile_id
    assert resolution.profile_version == 2


@pytest.mark.asyncio
async def test_expired_exact_profile_fails_closed_without_general_fallback() -> None:
    now = datetime.now(UTC)
    general = _profile(
        data_class="ALL_MEMORY",
        mode="STANDARD",
        effective_from=now - timedelta(days=3),
        expires_at=None,
    )
    expired_exact = _profile(
        data_class="PREFERENCE",
        effective_from=now - timedelta(days=3),
        expires_at=now - timedelta(days=1),
    )
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [general, expired_exact]
    session.execute.return_value = result

    resolution = await DecisionSupportProfileRepository(
        session,
        uuid4(),
    ).resolve_for_memory(elder_id=uuid4(), data_class="PREFERENCE", at=now)

    assert resolution.usable is False
    assert resolution.reason_code == "DECISION_SUPPORT_PROFILE_NOT_ACTIVE"


def test_supported_profile_turns_low_auto_activation_into_elder_confirmation() -> None:
    profile_id = uuid4()
    profile = DecisionSupportResolution(
        usable=True,
        mode="SUPPORTED",
        allowed_memory_risks=frozenset({"LOW", "MEDIUM"}),
        profile_id=profile_id,
        profile_version=4,
        data_class="PREFERENCE",
        reason_code="DECISION_SUPPORT_PROFILE_ACTIVE",
    )

    result = apply_decision_support_profile(_low_decision(), profile)

    assert result.allowed is True
    assert result.decision.status == "PENDING_CONFIRMATION"
    assert result.decision.policy_decision == "PENDING_SUPPORTED_CONFIRMATION"
    assert result.decision.required_verification == "SUPPORTED_ELDER_CONFIRMATION"
    assert profile_binding_is_current(
        bound_profile_id=profile_id,
        bound_profile_version=4,
        current=profile,
    )


def test_representative_required_never_substitutes_for_elder_confirmation() -> None:
    profile = DecisionSupportResolution(
        usable=True,
        mode="REPRESENTATIVE_REQUIRED",
        allowed_memory_risks=frozenset(),
        profile_id=uuid4(),
        profile_version=1,
        data_class="PREFERENCE",
        reason_code="DECISION_SUPPORT_PROFILE_ACTIVE",
    )

    result = apply_decision_support_profile(_low_decision(), profile)

    assert result.allowed is False
    assert result.reason_code == "REPRESENTATIVE_REQUIRED_NO_ELDER_MEMORY"
