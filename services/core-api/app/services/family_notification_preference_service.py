"""Manage only the authenticated family's daily LINE opt-in for one elder."""

from datetime import UTC, datetime, time
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError
from app.events.outbox_writer import write_outbox_entry
from app.models.notification import NotificationPreference
from app.repositories.family_notification_preference_repo import (
    FamilyNotificationPreferenceRepository,
)
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.family_notification_preference import (
    FamilyLineNotificationPreferenceResponse,
    UpdateFamilyLineNotificationPreference,
)
from app.services.authorization_service import authorize_elder
from app.services.consent_service import ConsentService
from app.services.line_subject_cipher import LineSubjectCipher

DAILY_SEND_TIME = time(8, 0)


def supported_daily_preference(preference: NotificationPreference | None) -> bool:
    """Do not silently replace another channel's schedule or quiet hours."""
    return preference is None or (
        preference.frequency == "DAILY"
        and preference.timezone == "Asia/Taipei"
        and (
            preference.send_time_local == DAILY_SEND_TIME
            or (preference.send_time_local is None and "LINE" not in preference.channels)
        )
        and not preference.quiet_hours
        and preference.status == "ACTIVE"
    )


class FamilyNotificationPreferenceService:
    def __init__(
        self,
        session: AsyncSession,
        actor: ActorContext,
        settings: Settings,
        *,
        subject_cipher: LineSubjectCipher | None = None,
    ) -> None:
        self._session = session
        self._actor = actor
        self._settings = settings
        self._cipher = subject_cipher
        self._repository = FamilyNotificationPreferenceRepository(
            session, actor.tenant_id, actor.actor_id
        )

    async def _require_access(self, elder_id: UUID):
        if self._actor.actor_role != "FAMILY_MEMBER" or self._actor.status != "ACTIVE":
            raise NotFoundError("Resource not found")
        await authorize_elder(self._session, self._actor, elder_id, "family_report:read")
        consent = await ConsentService(self._session, self._actor.tenant_id).require_active(
            elder_id=elder_id,
            purpose="FAMILY_SHARING",
        )
        if not await self._repository.has_daily_relationship(
            elder_id, consent.id, datetime.now(UTC)
        ):
            raise NotFoundError("Resource not found")
        return consent

    async def _preference(self, elder_id: UUID, *, lock: bool = False):
        return await self._repository.get_for_actor(elder_id, lock=lock)

    async def _response(self, elder_id: UUID, preference):
        identity = await self._repository.active_line_identity()
        line_status = "UNLINKED"
        if identity is not None:
            line_status = "RELINK_REQUIRED"
            if identity.encrypted_external_subject:
                line_status = "LINKED"
                if self._cipher is not None:
                    try:
                        self._cipher.decrypt(identity.encrypted_external_subject)
                    except ValueError:
                        line_status = "RELINK_REQUIRED"
        available = (
            self._settings.line_daily_notification_enabled
            and self._settings.line_account_link_enabled
        )
        if not supported_daily_preference(preference):
            availability = "UNSUPPORTED_SCHEDULE"
        elif not available:
            availability = "SERVICE_UNAVAILABLE"
        elif line_status != "LINKED":
            availability = "LINE_LINK_REQUIRED"
        else:
            availability = "READY"
        return FamilyLineNotificationPreferenceResponse(
            elder_id=elder_id,
            preference_id=preference.id if preference else None,
            line_enabled=bool(preference and "LINE" in preference.channels),
            version=preference.version if preference else 0,
            line_status=line_status,
            availability=availability,
            line_link_available=self._settings.line_account_link_enabled,
            can_enable=availability == "READY",
            updated_at=preference.updated_at if preference else None,
        )

    async def get(self, elder_id: UUID):
        await self._require_access(elder_id)
        return await self._response(elder_id, await self._preference(elder_id))

    async def update(
        self,
        elder_id: UUID,
        request: UpdateFamilyLineNotificationPreference,
        *,
        idempotency_key: str,
        trace_id: str,
    ):
        await self._require_access(elder_id)
        # The parent row serializes both the missing-row create and updates.
        elder = await self._repository.lock_elder(elder_id)
        if elder is None:
            raise NotFoundError("Resource not found")
        consent = await self._require_access(elder_id)
        idem = IdempotencyRepository(self._session, self._actor.tenant_id, self._actor.actor_id)
        replay = await idem.begin(
            key=idempotency_key,
            operation="update_family_line_notification_preference",
            payload={"elder_id": str(elder_id), **request.model_dump(mode="json")},
        )
        # Lock waits may outlive an authorization; replay must also recheck it.
        consent = await self._require_access(elder_id)
        if replay.replayed and replay.response_body is not None:
            return FamilyLineNotificationPreferenceResponse.model_validate(replay.response_body)
        if replay.replayed:
            raise ConflictError("Notification preference replay is unavailable")
        preference = await self._preference(elder_id, lock=True)
        current = await self._response(elder_id, preference)
        if request.expected_version != current.version:
            raise ConflictError("Notification preference version conflict")
        if request.line_enabled and not current.can_enable:
            raise ConflictError("LINE notification is not ready; reload the current settings")
        if preference is None:
            preference = NotificationPreference(
                id=uuid4(),
                family_actor_id=self._actor.actor_id,
                elder_id=elder_id,
                channels=[],
                frequency="DAILY",
                send_time_local=DAILY_SEND_TIME,
                timezone="Asia/Taipei",
                quiet_hours={},
                important_event_enabled=False,
                status="ACTIVE",
                version=1,
            )
        else:
            preference.version += 1
        channels = [channel for channel in preference.channels if channel != "LINE"]
        if request.line_enabled:
            channels.append("LINE")
            if preference.send_time_local is None:
                preference.send_time_local = DAILY_SEND_TIME
        preference.channels = channels
        await self._repository.save(preference)
        await write_outbox_entry(
            self._session,
            event_type="family.notification_preference.updated.v1",
            aggregate_type="notification_preference",
            aggregate_id=preference.id,
            aggregate_version=preference.version,
            tenant_id=self._actor.tenant_id,
            elder_id=elder_id,
            actor_id=self._actor.actor_id,
            purpose="FAMILY_SHARING",
            consent_version=consent.version,
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
            payload={"line_enabled": request.line_enabled, "version": preference.version},
        )
        response = await self._response(elder_id, preference)
        await idem.complete(
            key=idempotency_key,
            resource_type="notification_preference",
            resource_id=preference.id,
            response_status=200,
            response_body=response.model_dump(mode="json"),
        )
        return response
