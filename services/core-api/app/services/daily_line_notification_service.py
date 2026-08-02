"""08:00 Asia/Taipei delivery of the previous day's published family reports."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.adapters.line_messaging import (
    LineDailyReportNotice,
    LineMessagingClient,
)
from app.core.exceptions import ServiceUnavailableError
from app.db.engine import DatabaseEngine
from app.repositories.notification_repo import DailyLineCandidate, NotificationRepository
from app.schemas.notification import (
    DailyLineDeliveryResult,
    DailyLineNotificationCounts,
    DailyLineNotificationJobRequest,
    DailyLineNotificationJobResponse,
    NotificationSourcePeriod,
)
from app.services.line_subject_cipher import LineSubjectCipher

_DELIVERY_NAMESPACE = uuid.UUID("98b6f0fa-475a-4e75-9126-956158840f2b")
_MAX_ATTEMPTS = 3
_MAX_CONCURRENCY = 4


class DailyLineNotificationService:
    """Discover, reauthorize, claim, and deliver one tenant's daily reminders."""

    def __init__(
        self,
        db_engine: DatabaseEngine,
        *,
        tenant_id: UUID,
        line_client: LineMessagingClient,
        subject_cipher: LineSubjectCipher,
        family_report_url: str,
        send_time_local: str = "08:00",
    ) -> None:
        self._db_engine = db_engine
        self._tenant_id = tenant_id
        self._line_client = line_client
        self._subject_cipher = subject_cipher
        self._family_report_url = family_report_url.rstrip("/") + "/family/reports"
        hour, minute = (int(part) for part in send_time_local.split(":"))
        self._send_time = time(hour, minute)

    async def run(
        self,
        request: DailyLineNotificationJobRequest,
    ) -> DailyLineNotificationJobResponse:
        scheduled_at = request.scheduled_for.astimezone(UTC)
        local_scheduled_at = scheduled_at.astimezone(ZoneInfo(request.timezone))
        source_date = local_scheduled_at.date() - timedelta(days=1)
        now = datetime.now(UTC)
        async with self._db_engine.session_factory() as session:
            candidates = await NotificationRepository(
                session,
                self._tenant_id,
            ).list_daily_line_candidates(
                source_date=source_date,
                timezone=request.timezone,
                send_time=self._send_time,
                now=now,
            )

        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def deliver(candidate: DailyLineCandidate) -> DailyLineDeliveryResult:
            async with semaphore:
                return await self._deliver_one(
                    candidate,
                    source_date=source_date,
                    timezone=request.timezone,
                    scheduled_at=scheduled_at,
                )

        deliveries = await asyncio.gather(*(deliver(item) for item in candidates))
        sent = sum(item.status == "SENT" for item in deliveries)
        replayed = sum(item.status == "REPLAYED" for item in deliveries)
        skipped = sum(item.status == "SKIPPED" for item in deliveries)
        failed = sum(item.status == "FAILED" for item in deliveries)
        if not candidates:
            job_status = "NO_ELIGIBLE_REPORTS"
        elif failed:
            job_status = "PARTIAL_FAILURE"
        else:
            job_status = "COMPLETED"
        return DailyLineNotificationJobResponse(
            status=job_status,
            scheduled_for=scheduled_at,
            timezone=request.timezone,
            source_period=NotificationSourcePeriod(
                start=source_date.isoformat(),
                end=source_date.isoformat(),
            ),
            counts=DailyLineNotificationCounts(
                eligible=len(candidates),
                sent=sent,
                replayed=replayed,
                skipped=skipped,
                failed=failed,
            ),
            deliveries=deliveries,
        )

    async def _deliver_one(
        self,
        candidate: DailyLineCandidate,
        *,
        source_date: date,
        timezone: str,
        scheduled_at: datetime,
    ) -> DailyLineDeliveryResult:
        fallback_id = self._delivery_id(candidate, scheduled_at)
        try:
            now = datetime.now(UTC)
            async with self._db_engine.session_factory() as session:
                repository = NotificationRepository(session, self._tenant_id)
                fresh_candidates = await repository.list_daily_line_candidates(
                    source_date=source_date,
                    timezone=timezone,
                    send_time=self._send_time,
                    now=now,
                    report_id=candidate.report_id,
                    recipient_actor_id=candidate.recipient_actor_id,
                )
                fresh = next(
                    (
                        item
                        for item in fresh_candidates
                        if item.report_version == candidate.report_version
                        and item.report_version_id == candidate.report_version_id
                    ),
                    None,
                )
                if fresh is None:
                    return self._result(
                        candidate,
                        fallback_id,
                        "SKIPPED",
                        "ELIGIBILITY_CHANGED",
                    )
                claim = await repository.claim_delivery(
                    candidate=fresh,
                    scheduled_at=scheduled_at,
                    now=now,
                    max_attempts=_MAX_ATTEMPTS,
                )
                await session.commit()
            if claim.status != "CLAIMED":
                return self._result(
                    candidate,
                    claim.notification_id,
                    claim.status,
                    claim.reason_code,
                )

            try:
                line_user_id = self._subject_cipher.decrypt(fresh.encrypted_subject)
            except ValueError:
                await self._mark_failed(
                    claim.notification_id,
                    "LINE_TARGET_DECRYPTION_FAILED",
                    terminal=True,
                )
                return self._result(
                    candidate,
                    claim.notification_id,
                    "FAILED",
                    "LINE_TARGET_DECRYPTION_FAILED",
                )

            try:
                await self._line_client.push_daily_report(
                    line_user_id=line_user_id,
                    notice=LineDailyReportNotice(
                        report_date=source_date.isoformat(),
                        action_url=self._family_report_url,
                    ),
                    retry_key=str(claim.notification_id),
                )
            except ServiceUnavailableError:
                await self._mark_failed(
                    claim.notification_id,
                    "LINE_PROVIDER_UNAVAILABLE",
                )
                return self._result(
                    candidate,
                    claim.notification_id,
                    "FAILED",
                    "LINE_PROVIDER_UNAVAILABLE",
                )

            async with self._db_engine.session_factory() as session:
                await NotificationRepository(session, self._tenant_id).mark_sent(
                    claim.notification_id,
                    now=datetime.now(UTC),
                )
                await session.commit()
            return self._result(candidate, claim.notification_id, "SENT", None)
        except Exception:  # candidate isolation; response never includes exception text
            return self._result(
                candidate,
                fallback_id,
                "FAILED",
                "DELIVERY_PROCESSING_FAILED",
            )

    async def _mark_failed(
        self,
        notification_id: UUID,
        reason_code: str,
        *,
        terminal: bool = False,
    ) -> None:
        async with self._db_engine.session_factory() as session:
            await NotificationRepository(session, self._tenant_id).mark_failed(
                notification_id,
                reason_code=reason_code,
                terminal=terminal,
            )
            await session.commit()

    @staticmethod
    def _delivery_id(candidate: DailyLineCandidate, scheduled_at: datetime) -> UUID:
        key = (
            f"line-daily:{candidate.report_id}:{candidate.report_version}:"
            f"{candidate.recipient_actor_id}:{scheduled_at.isoformat()}"
        )
        return uuid.uuid5(_DELIVERY_NAMESPACE, key)

    @staticmethod
    def _result(
        candidate: DailyLineCandidate,
        notification_id: UUID,
        status: str,
        reason_code: str | None,
    ) -> DailyLineDeliveryResult:
        return DailyLineDeliveryResult(
            notification_id=notification_id,
            report_id=candidate.report_id,
            report_version=candidate.report_version,
            status=status,
            reason_code=reason_code,
        )
