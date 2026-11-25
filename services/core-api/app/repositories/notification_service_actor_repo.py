"""Fetch only the server-configured notification service actor."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor


async def get_notification_service_actor(session: AsyncSession, actor_id: UUID) -> Actor | None:
    return await session.scalar(
        select(Actor)
        .where(Actor.id == actor_id, Actor.actor_type == "SYSTEM_SERVICE", Actor.status == "ACTIVE")
        .execution_options(populate_existing=True)
    )
