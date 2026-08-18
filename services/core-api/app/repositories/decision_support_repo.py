"""Tenant-scoped resolution of append-only DecisionSupportProfile rows."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.models.decision_support import DecisionSupportProfile
from app.policies.decision_support import (
    DECISION_SCOPE_MEMORY_CONFIRMATION,
    DECISION_SUPPORT_MODES,
    MEMORY_PROFILE_RISKS,
    DecisionSupportResolution,
    blocked_resolution,
    default_standard_resolution,
)
from app.policies.memory_policy import CURRENT_MEMORY_POLICY_VERSION
from app.repositories.base import BaseRepository


class DecisionSupportProfileRepository(BaseRepository):
    """Resolve current policy metadata without reading restricted clinical text."""

    async def resolve_for_memory(
        self,
        *,
        elder_id: UUID,
        data_class: str,
        at: datetime | None = None,
    ) -> DecisionSupportResolution:
        result = await self._session.execute(
            select(DecisionSupportProfile)
            .where(
                DecisionSupportProfile.tenant_id == self._tenant_id,
                DecisionSupportProfile.elder_id == elder_id,
                DecisionSupportProfile.decision_scope == DECISION_SCOPE_MEMORY_CONFIRMATION,
                DecisionSupportProfile.data_class.in_([data_class, "ALL_MEMORY"]),
            )
            .order_by(
                DecisionSupportProfile.data_class.desc(),
                DecisionSupportProfile.profile_version.desc(),
            )
        )
        rows = list(result.scalars().all())
        exact = [row for row in rows if row.data_class == data_class]
        applicable = exact if exact else [row for row in rows if row.data_class == "ALL_MEMORY"]
        if not applicable:
            return default_standard_resolution(data_class)

        now = at or datetime.now(UTC)
        active = [
            row
            for row in applicable
            if row.effective_from <= now and (row.expires_at is None or row.expires_at > now)
        ]
        if not active:
            return blocked_resolution(data_class, "DECISION_SUPPORT_PROFILE_NOT_ACTIVE")

        current = max(active, key=lambda row: row.profile_version)
        allowed_risks = frozenset(current.allowed_memory_risks)
        if (
            current.mode not in DECISION_SUPPORT_MODES
            or not current.basis_reference
            or current.policy_version != CURRENT_MEMORY_POLICY_VERSION
            or not allowed_risks.issubset(MEMORY_PROFILE_RISKS)
            or (current.mode == "REPRESENTATIVE_REQUIRED" and allowed_risks)
        ):
            return blocked_resolution(data_class, "DECISION_SUPPORT_PROFILE_INVALID")

        return DecisionSupportResolution(
            usable=True,
            mode=current.mode,
            allowed_memory_risks=allowed_risks,
            profile_id=current.decision_support_profile_id,
            profile_version=current.profile_version,
            data_class=current.data_class,
            reason_code="DECISION_SUPPORT_PROFILE_ACTIVE",
        )
