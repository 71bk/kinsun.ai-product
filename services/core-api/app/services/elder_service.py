"""ElderService — application service for authorized Elder data access.

Orchestrates Elder existence checks with ElderAccessPolicy evaluation.
Both methods follow the non-disclosure pattern: unauthorized and nonexistent
elders return None, which the handler layer converts to a 404 ErrorEnvelope.

No exceptions are raised for authorization failures — the uniform None return
prevents response path divergence that could leak Elder existence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from app.models.elder import Elder
from app.policies.elder_access import (
    ElderAccessDecision,
    ElderAccessPolicy,
    ElderAccessRequest,
)
from app.repositories.elder_repo import ElderRepository


@dataclass(frozen=True)
class AccessContext:
    """Summary of an actor's authorization scope for a specific Elder.

    Returned by get_access_context when the actor is authorized.

    Attributes:
        purpose: Description of access purpose (e.g. "elder_care_access").
        allowed_actions: The granted scope list from the authorization source.
        source_type: "relationship" or "assignment".
        source_summary: Human-readable summary (e.g. "FAMILY_SHARE relationship").
        expires_at: Earliest expiry time from the authorization source, or None.
    """

    purpose: str
    allowed_actions: list[str]
    source_type: str | None
    source_summary: str
    expires_at: datetime | None


class ElderService:
    """Application service for authorized Elder data retrieval.

    Combines existence checking with policy evaluation to implement
    the non-disclosure pattern. Both public methods return None when
    the elder doesn't exist OR the actor isn't authorized — the handler
    converts None to a 404 response.

    Dependencies are injected via constructor for testability.
    """

    def __init__(
        self,
        elder_repo: ElderRepository,
        elder_access_policy: ElderAccessPolicy,
    ) -> None:
        """Initialize ElderService with repository and policy dependencies.

        Args:
            elder_repo: Repository for Elder entity queries (tenant-scoped).
            elder_access_policy: Policy evaluator for Elder access decisions.
        """
        self._elder_repo = elder_repo
        self._policy = elder_access_policy

    async def get_elder_if_authorized(self, access_request: ElderAccessRequest) -> Elder | None:
        """Check existence AND authorization, returning the Elder or None.

        Implements the non-disclosure pattern:
        - Elder doesn't exist in this tenant → return None
        - Elder exists but actor isn't authorized → return None
        - Elder exists and actor is authorized → return the Elder entity

        The handler layer converts None → 404 ErrorEnvelope. There is no
        branch divergence between "not found" and "unauthorized" responses.

        Args:
            access_request: The fully-constructed access request containing
                actor_id, actor_role, tenant_id, elder_id, requested_action,
                and current_time.

        Returns:
            The Elder entity if found and authorized, or None.
        """
        # Step 1: Check if elder exists in this tenant
        elder = await self._elder_repo.get_by_id(access_request.elder_id)
        if elder is None:
            return None

        # Step 2: Evaluate authorization policy
        if access_request.actor_role == "ELDER":
            access_request = replace(
                access_request,
                actor_is_elder_self=elder.actor_id == access_request.actor_id,
            )
        decision: ElderAccessDecision = await self._policy.check_access(access_request)
        if not decision.allowed:
            return None

        # Step 3: Access granted — return the elder entity
        return elder

    async def get_access_context(self, access_request: ElderAccessRequest) -> AccessContext | None:
        """Return the authorization scope summary for an actor's Elder access.

        Implements the non-disclosure pattern:
        - Elder doesn't exist in this tenant → return None
        - Elder exists but actor isn't authorized → return None
        - Elder exists and actor is authorized → return AccessContext

        The handler layer converts None → 404 ErrorEnvelope.

        Args:
            access_request: The fully-constructed access request containing
                actor_id, actor_role, tenant_id, elder_id, requested_action,
                and current_time.

        Returns:
            AccessContext with authorization details if authorized, or None.
        """
        # Step 1: Check if elder exists in this tenant
        exists = await self._elder_repo.exists(access_request.elder_id)
        if not exists:
            return None

        # Step 2: Evaluate authorization policy
        if access_request.actor_role == "ELDER":
            elder = await self._elder_repo.get_by_id(access_request.elder_id)
            if elder is None:
                return None
            access_request = replace(
                access_request,
                actor_is_elder_self=elder.actor_id == access_request.actor_id,
            )
        decision: ElderAccessDecision = await self._policy.check_access(access_request)
        if not decision.allowed:
            return None

        # Step 3: Build AccessContext from the decision
        source_summary = self._build_source_summary(decision)

        return AccessContext(
            purpose="elder_care_access",
            allowed_actions=decision.granted_scope,
            source_type=decision.source_type,
            source_summary=source_summary,
            expires_at=decision.expires_at,
        )

    @staticmethod
    def _build_source_summary(decision: ElderAccessDecision) -> str:
        """Build a human-readable summary of the authorization source.

        Args:
            decision: The allowed access decision from the policy.

        Returns:
            A string like "FAMILY_SHARE relationship" or "HOME_CARE assignment".
        """
        if decision.source_type == "relationship":
            return f"{decision.source_type} authorization"
        elif decision.source_type == "assignment":
            return f"{decision.source_type} authorization"
        elif decision.source_type == "elder_self":
            return "elder self authorization"
        return "unknown authorization source"
