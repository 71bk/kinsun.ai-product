"""Shared Elder authorization composition for all Core Domain APIs."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.policies.elder_access import ElderAccessDecision, ElderAccessPolicy, ElderAccessRequest
from app.repositories.care_assignment_repo import CareAssignmentRepository
from app.repositories.care_relationship_repo import CareRelationshipRepository
from app.repositories.care_unit_membership_repo import CareUnitMembershipRepository
from app.repositories.elder_repo import ElderRepository
from app.repositories.tenant_membership_repo import TenantMembershipRepository


async def authorize_elder(
    session: AsyncSession,
    actor_context: ActorContext,
    elder_id: UUID,
    requested_action: str,
) -> None:
    """Authorize against live DB state and hide existence on denial."""
    await authorize_elder_with_decision(
        session,
        actor_context,
        elder_id,
        requested_action,
    )


async def authorize_elder_with_decision(
    session: AsyncSession,
    actor_context: ActorContext,
    elder_id: UUID,
    requested_action: str,
) -> ElderAccessDecision:
    """Authorize and retain the server-derived relationship/assignment reference."""
    elder_repo = ElderRepository(session, actor_context.tenant_id)
    elder = await elder_repo.get_by_id(elder_id)
    if elder is None:
        raise NotFoundError("Resource not found")

    policy = ElderAccessPolicy(
        tenant_membership_repo=TenantMembershipRepository(session),
        care_unit_membership_repo=CareUnitMembershipRepository(session),
        care_relationship_repo=CareRelationshipRepository(
            session,
            actor_context.tenant_id,
        ),
        care_assignment_repo=CareAssignmentRepository(
            session,
            actor_context.tenant_id,
        ),
    )
    decision = await policy.check_access(
        ElderAccessRequest(
            actor_id=actor_context.actor_id,
            actor_role=actor_context.actor_role,
            tenant_id=actor_context.tenant_id,
            elder_id=elder_id,
            requested_action=requested_action,
            current_time=datetime.now(UTC),
            actor_is_elder_self=elder.actor_id == actor_context.actor_id,
        )
    )
    if not decision.allowed:
        raise NotFoundError("Resource not found")
    return decision
