"""Pre-service preview is not an elder-data access grant."""

from dataclasses import dataclass
from datetime import datetime

from app.core.auth import ActorContext
from app.core.cursor import decode_cursor, encode_cursor
from app.core.exceptions import AuthorizationDeniedError, ValidationError
from app.repositories.home_care_schedule_repo import HomeCareScheduleRepository


@dataclass(frozen=True)
class HomeCareSchedulePage:
    items: list
    as_of: datetime
    next_cursor: str | None
    has_more: bool
    limit: int


async def get_home_care_schedule(
    session, actor: ActorContext, now: datetime, cursor: str | None, limit: int
):
    if actor.actor_role != "HOME_CARE_WORKER" or actor.status != "ACTIVE":
        raise AuthorizationDeniedError("Resource not found")
    after = decode_cursor(cursor) if cursor else None
    if after is not None and after[0].utcoffset() is None:
        raise ValidationError(details=[{"field": "cursor", "reason": "cursor is invalid"}])
    rows = await HomeCareScheduleRepository(session, actor.tenant_id).list_today(
        actor.actor_id, now, after, limit
    )
    items = list(rows[:limit])
    more = len(rows) > limit
    next_cursor = (
        encode_cursor(items[-1]["scheduled_start"], items[-1]["assignment_id"]) if more else None
    )
    return HomeCareSchedulePage(items, now, next_cursor, more, limit)
