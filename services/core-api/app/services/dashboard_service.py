"""Bounded, live-authorized caregiver dashboard counts."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.repositories.care_action_repo import CareActionRepository
from app.repositories.care_event_repo import CareEventRepository
from app.services.authorization_service import authorize_elder
from app.services.care_action_service import PROFESSIONAL_CARE_ROLES


async def get_open_care_action_counts(
    session: AsyncSession, actor: ActorContext, elder_ids: list[UUID]
) -> dict[UUID, int]:
    """Reauthorize the returned page using the same gate as care-action list.

    Missing entries mean unavailable, never zero. Family callers cannot obtain
    professional task metadata even if a legacy share includes care_action:read.
    Reuse the canonical live policy instead of inventing a second SQL auth rule.
    Authorization is sequential (one AsyncSession); counting is one grouped query.
    """
    if actor.actor_role not in PROFESSIONAL_CARE_ROLES:
        return {}
    allowed = []
    for elder_id in dict.fromkeys(elder_ids):
        try:
            await authorize_elder(session, actor, elder_id, "care_action:read")
        except NotFoundError:
            continue
        allowed.append(elder_id)
    counts = await CareActionRepository(session, actor.tenant_id).count_open_by_elder(allowed)
    return {elder_id: counts.get(elder_id, 0) for elder_id in allowed}


async def get_pending_event_review_counts(
    session: AsyncSession, actor: ActorContext, elder_ids: list[UUID]
) -> dict[UUID, int]:
    """Match both gates of explicit non-formal care-event listing.

    A review count is private metadata: neither read-only access nor family
    access can reveal it. Operational errors propagate instead of becoming zero.
    """
    if actor.actor_role not in PROFESSIONAL_CARE_ROLES:
        return {}
    allowed = []
    for elder_id in dict.fromkeys(elder_ids):
        try:
            await authorize_elder(session, actor, elder_id, "care_event:read")
            await authorize_elder(session, actor, elder_id, "care_event:review")
        except NotFoundError:
            continue
        allowed.append(elder_id)
    counts = await CareEventRepository(session, actor.tenant_id).count_pending_review_by_elder(
        allowed
    )
    return {elder_id: counts.get(elder_id, 0) for elder_id in allowed}
