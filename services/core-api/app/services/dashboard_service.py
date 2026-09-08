"""Bounded, live-authorized caregiver dashboard counts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.repositories.care_action_repo import CareActionRepository
from app.repositories.care_event_repo import CareEventRepository
from app.repositories.conversation_repo import ConversationRepository, InteractionMetrics
from app.repositories.summary_repo import DailySummarySnapshot, SummaryRepository
from app.services.authorization_service import authorize_elder
from app.services.care_action_service import PROFESSIONAL_CARE_ROLES


async def get_daily_summary_snapshots(
    session: AsyncSession, actor: ActorContext, elder_ids: list[UUID], as_of: datetime
) -> dict[UUID, DailySummarySnapshot]:
    """Reuse summary read/review gates; a hidden draft must not reveal existence."""
    if actor.actor_role not in PROFESSIONAL_CARE_ROLES:
        return {}
    allowed, reviewers = [], []
    for elder_id in dict.fromkeys(elder_ids):
        try:
            await authorize_elder(session, actor, elder_id, "summary:read")
        except NotFoundError:
            continue
        allowed.append(elder_id)
        try:
            await authorize_elder(session, actor, elder_id, "summary:review")
        except NotFoundError:
            continue
        reviewers.append(elder_id)
    snapshots = await SummaryRepository(session, actor.tenant_id).dashboard_snapshots(
        allowed, reviewers, as_of
    )
    return {elder_id: snapshots[elder_id] for elder_id in allowed if elder_id in snapshots}


async def get_interaction_metrics(
    session: AsyncSession, actor: ActorContext, elder_ids: list[UUID], as_of: datetime
) -> dict[UUID, InteractionMetrics]:
    """Use the existing session-metadata read gate; never disclose to family."""
    if actor.actor_role not in PROFESSIONAL_CARE_ROLES:
        return {}
    allowed = []
    for elder_id in dict.fromkeys(elder_ids):
        try:
            await authorize_elder(session, actor, elder_id, "voice_session:read")
        except NotFoundError:
            continue
        allowed.append(elder_id)
    metrics = await ConversationRepository(session, actor.tenant_id).interaction_metrics_by_elder(
        allowed, as_of
    )
    return {elder_id: metrics[elder_id] for elder_id in allowed if elder_id in metrics}


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
