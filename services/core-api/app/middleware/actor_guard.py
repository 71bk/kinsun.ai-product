"""Actor status and service-role guards for protected Core operations."""

from __future__ import annotations

from fastapi import Depends

from app.core.exceptions import AuthorizationDeniedError
from app.middleware.auth import ActorContext, get_actor_context
from app.models.enums import ActorType
from app.policies import ActorInactiveError


async def require_active_actor(
    actor: ActorContext = Depends(get_actor_context),
) -> ActorContext:
    """Reject non-ACTIVE actors before any business operation."""
    if actor.status != "ACTIVE":
        raise ActorInactiveError(
            f"Actor status is {actor.status}. Only ACTIVE actors may perform this operation."
        )
    return actor


async def require_system_service_actor(
    actor: ActorContext = Depends(require_active_actor),
) -> ActorContext:
    """Allow internal routes only for an active system service."""
    if actor.actor_role != ActorType.SYSTEM_SERVICE.value:
        raise AuthorizationDeniedError("Resource not found")
    return actor
