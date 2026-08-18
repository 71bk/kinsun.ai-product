"""Elder API endpoints — authorized Elder data access.

Provides:
- GET /api/v1/elders/{elder_id} → ElderResponse (basic profile)
- GET /api/v1/elders/{elder_id}/access-context → AccessContextResponse

Both endpoints follow the non-disclosure pattern: unauthorized and
nonexistent elders produce the same 404 response to prevent leaking
Elder existence to unauthorized actors.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import success
from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.policies.elder_access import ElderAccessPolicy, ElderAccessRequest
from app.repositories.care_assignment_repo import CareAssignmentRepository
from app.repositories.care_relationship_repo import CareRelationshipRepository
from app.repositories.care_unit_membership_repo import CareUnitMembershipRepository
from app.repositories.elder_repo import ElderRepository
from app.repositories.tenant_membership_repo import TenantMembershipRepository
from app.schemas.elder import AccessContextResponse, ElderResponse
from app.services.elder_service import ElderService

router = APIRouter(prefix="/api/v1", tags=["elders"])


def _build_elder_service(session: AsyncSession, tenant_id: UUID) -> ElderService:
    """Construct ElderService with all repository and policy dependencies.

    Args:
        session: The request-scoped async database session.
        tenant_id: The actor's tenant ID for tenant-scoped repositories.

    Returns:
        A fully-wired ElderService instance.
    """
    # Repositories
    elder_repo = ElderRepository(session, tenant_id)
    tenant_membership_repo = TenantMembershipRepository(session)
    care_unit_membership_repo = CareUnitMembershipRepository(session)
    care_relationship_repo = CareRelationshipRepository(session, tenant_id)
    care_assignment_repo = CareAssignmentRepository(session, tenant_id)

    # Policy
    policy = ElderAccessPolicy(
        tenant_membership_repo=tenant_membership_repo,
        care_unit_membership_repo=care_unit_membership_repo,
        care_relationship_repo=care_relationship_repo,
        care_assignment_repo=care_assignment_repo,
    )

    # Service
    return ElderService(
        elder_repo=elder_repo,
        elder_access_policy=policy,
    )


@router.get("/elders/{elder_id}")
async def get_elder(
    elder_id: UUID = Path(..., description="The elder's UUID"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve basic Elder profile by ID.

    Implements the non-disclosure pattern: returns 404 for both
    nonexistent and unauthorized elders — no branch divergence.

    Requires action: elder:basic:read
    """
    access_request = ElderAccessRequest(
        actor_id=actor_context.actor_id,
        actor_role=actor_context.actor_role,
        tenant_id=actor_context.tenant_id,
        elder_id=elder_id,
        requested_action="elder:basic:read",
        current_time=datetime.now(UTC),
    )

    elder_service = _build_elder_service(session, actor_context.tenant_id)
    elder = await elder_service.get_elder_if_authorized(access_request)

    if elder is None:
        raise NotFoundError("Resource not found")

    elder_response = ElderResponse(
        elder_id=elder.id,
        display_name=elder.display_name,
        primary_care_setting=elder.primary_care_setting,
        status=elder.status,
    )

    return success(elder_response.model_dump(mode="json"))


@router.get("/elders/{elder_id}/access-context")
async def get_elder_access_context(
    elder_id: UUID = Path(..., description="The elder's UUID"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve the actor's authorization scope for a specific Elder.

    Implements the non-disclosure pattern: returns 404 for both
    nonexistent and unauthorized elders — no branch divergence.

    Requires action: elder:access_context:read
    """
    access_request = ElderAccessRequest(
        actor_id=actor_context.actor_id,
        actor_role=actor_context.actor_role,
        tenant_id=actor_context.tenant_id,
        elder_id=elder_id,
        requested_action="elder:access_context:read",
        current_time=datetime.now(UTC),
    )

    elder_service = _build_elder_service(session, actor_context.tenant_id)
    access_context = await elder_service.get_access_context(access_request)

    if access_context is None:
        raise NotFoundError("Resource not found")

    response = AccessContextResponse(
        purpose=access_context.purpose,
        allowed_actions=access_context.allowed_actions,
        source_type=access_context.source_type,
        source_summary=access_context.source_summary,
        expires_at=access_context.expires_at,
    )

    return success(response.model_dump(mode="json"))
