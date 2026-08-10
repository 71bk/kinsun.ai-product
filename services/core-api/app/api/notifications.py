"""Trusted scheduler endpoint for daily LINE family-report notifications."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.responses import success
from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceUnavailableError
from app.db.engine import DatabaseEngine
from app.db.session import get_db_engine
from app.middleware.actor_guard import require_system_service_actor
from app.middleware.auth import ActorContext
from app.schemas.notification import DailyLineNotificationJobRequest
from app.services.daily_line_notification_service import DailyLineNotificationService
from app.services.service_dependencies import (
    get_line_messaging_client,
    get_line_subject_cipher,
)

router = APIRouter(prefix="/api/v1/internal/notification-jobs", tags=["notifications"])


@router.post("/line-daily")
async def run_daily_line_notifications(
    request: DailyLineNotificationJobRequest,
    actor: ActorContext = Depends(require_system_service_actor),
    db_engine: DatabaseEngine = Depends(get_db_engine),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not settings.line_daily_notification_enabled:
        raise ServiceUnavailableError("LINE daily notifications are unavailable")
    if not db_engine.is_ready:
        raise ServiceUnavailableError("Database is unavailable")
    result = await DailyLineNotificationService(
        db_engine,
        tenant_id=actor.tenant_id,
        line_client=get_line_messaging_client(),
        subject_cipher=get_line_subject_cipher(),
        family_report_url=settings.line_account_link_base_url,
        send_time_local=settings.line_daily_notification_send_time,
    ).run(request)
    return success(result.model_dump(mode="json"))
