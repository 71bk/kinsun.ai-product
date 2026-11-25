"""Family-owned notification settings, independently of contract signatory."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.auth import ActorContext
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.schemas.family_notification_preference import UpdateFamilyLineNotificationPreference
from app.services.family_notification_preference_service import FamilyNotificationPreferenceService
from app.services.line_subject_cipher import LineSubjectCipher

router = APIRouter(prefix="/api/v1/family", tags=["family-notification-preferences"])


def _service(session, actor, settings):
    cipher = (
        LineSubjectCipher(settings.line_subject_encryption_secret)
        if settings.line_daily_notification_enabled
        else None
    )
    return FamilyNotificationPreferenceService(session, actor, settings, subject_cipher=cipher)


@router.get("/elders/{elder_id}/line-notification-preference")
async def get_family_line_notification_preference(
    elder_id: UUID = Path(...),
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    response = await _service(session, actor, settings).get(elder_id)
    return success(response.model_dump(mode="json"))


@router.put("/elders/{elder_id}/line-notification-preference")
async def update_family_line_notification_preference(
    request: UpdateFamilyLineNotificationPreference,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    response = await _service(session, actor, settings).update(
        elder_id,
        request,
        idempotency_key=idempotency_key,
        trace_id=get_correlation_id(),
    )
    return success(response.model_dump(mode="json"))
