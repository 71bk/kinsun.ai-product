"""Tenant-safe candidate selection and durable notification delivery claims."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.consent import ConsentGrant
from app.models.elder import Elder
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.notification import NotificationDelivery, NotificationPreference
from app.models.report import FamilyRelationship, FamilyReport, ReportVersion
from app.models.tenant import Tenant

_DELIVERY_NAMESPACE = uuid.UUID("98b6f0fa-475a-4e75-9126-956158840f2b")
_SENDING_STALE_AFTER = timedelta(minutes=2)


@dataclass(frozen=True)
class DailyLineCandidate:
    report_id: UUID
    report_version_id: UUID
    report_version: int
    recipient_actor_id: UUID
    preference_id: UUID
    encrypted_subject: str


@dataclass(frozen=True)
class DeliveryClaim:
    notification_id: UUID
    status: str
    reason_code: str | None = None


class NotificationRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def list_daily_line_candidates(
        self,
        *,
        source_date: date,
        timezone: str,
        send_time: time,
        now: datetime,
        report_id: UUID | None = None,
        recipient_actor_id: UUID | None = None,
    ) -> list[DailyLineCandidate]:
        statement = (
            select(
                FamilyReport,
                ReportVersion,
                FamilyRelationship,
                NotificationPreference,
                ExternalIdentity,
            )
            .join(
                ReportVersion,
                (ReportVersion.report_id == FamilyReport.id)
                & (ReportVersion.version == FamilyReport.current_version),
            )
            .join(
                FamilyRelationship,
                FamilyRelationship.elder_id == FamilyReport.elder_id,
            )
            .join(
                NotificationPreference,
                (NotificationPreference.family_actor_id == FamilyRelationship.family_actor_id)
                & (NotificationPreference.elder_id == FamilyReport.elder_id),
            )
            .join(
                ExternalIdentity,
                ExternalIdentity.actor_id == FamilyRelationship.family_actor_id,
            )
            .join(Actor, Actor.id == FamilyRelationship.family_actor_id)
            .join(Elder, Elder.id == FamilyReport.elder_id)
            .join(Tenant, Tenant.id == FamilyReport.tenant_id)
            .join(ConsentGrant, ConsentGrant.id == FamilyRelationship.consent_id)
            .join(
                ActorTenantMembership,
                (ActorTenantMembership.actor_id == FamilyRelationship.family_actor_id)
                & (ActorTenantMembership.tenant_id == FamilyReport.tenant_id),
            )
            .where(
                FamilyReport.tenant_id == self._tenant_id,
                FamilyReport.report_type == "DAILY",
                FamilyReport.period_start == source_date,
                FamilyReport.period_end == source_date,
                FamilyReport.status == "PUBLISHED",
                Elder.status == "ACTIVE",
                Tenant.status == "ACTIVE",
                Actor.actor_type == "FAMILY_MEMBER",
                Actor.status == "ACTIVE",
                FamilyRelationship.status == "ACTIVE",
                FamilyRelationship.effective_from <= now,
                or_(
                    FamilyRelationship.effective_to.is_(None),
                    now < FamilyRelationship.effective_to,
                ),
                or_(
                    FamilyRelationship.share_scope.any("REPORT_DAILY"),
                    FamilyRelationship.share_scope.any("REPORT_ALL"),
                ),
                ConsentGrant.purpose_code == "FAMILY_SHARING",
                ConsentGrant.status == "GRANTED",
                ConsentGrant.effective_at <= now,
                or_(ConsentGrant.expires_at.is_(None), now < ConsentGrant.expires_at),
                or_(ConsentGrant.revoked_at.is_(None), now < ConsentGrant.revoked_at),
                NotificationPreference.status == "ACTIVE",
                NotificationPreference.frequency == "DAILY",
                NotificationPreference.timezone == timezone,
                NotificationPreference.send_time_local == send_time,
                NotificationPreference.channels.any("LINE"),
                ExternalIdentity.provider == "LINE",
                ExternalIdentity.status == "ACTIVE",
                ExternalIdentity.encrypted_external_subject.is_not(None),
                ActorTenantMembership.care_unit_id.is_(None),
                ActorTenantMembership.role_code == "FAMILY_MEMBER",
                ActorTenantMembership.status == "ACTIVE",
                ActorTenantMembership.effective_from <= now,
                or_(
                    ActorTenantMembership.effective_to.is_(None),
                    now < ActorTenantMembership.effective_to,
                ),
            )
        )
        if report_id is not None:
            statement = statement.where(FamilyReport.id == report_id)
        if recipient_actor_id is not None:
            statement = statement.where(FamilyRelationship.family_actor_id == recipient_actor_id)
        rows = (await self._session.execute(statement)).all()
        candidates: dict[tuple[UUID, UUID], DailyLineCandidate] = {}
        for report, version, relationship, preference, identity in rows:
            relationship_ids = report.recipient_scope.get("relationship_ids", [])
            if str(relationship.id) not in relationship_ids:
                continue
            key = (report.id, relationship.family_actor_id)
            candidates[key] = DailyLineCandidate(
                report_id=report.id,
                report_version_id=version.report_version_id,
                report_version=report.current_version,
                recipient_actor_id=relationship.family_actor_id,
                preference_id=preference.id,
                encrypted_subject=identity.encrypted_external_subject,
            )
        return list(candidates.values())[:500]

    async def claim_delivery(
        self,
        *,
        candidate: DailyLineCandidate,
        scheduled_at: datetime,
        now: datetime,
        max_attempts: int,
    ) -> DeliveryClaim:
        idempotency_key = (
            f"line-daily:{candidate.report_id}:{candidate.report_version}:"
            f"{candidate.recipient_actor_id}:{scheduled_at.isoformat()}"
        )
        notification_id = uuid.uuid5(_DELIVERY_NAMESPACE, idempotency_key)
        await self._session.execute(
            insert(NotificationDelivery)
            .values(
                notification_id=notification_id,
                report_id=candidate.report_id,
                report_version_id=candidate.report_version_id,
                recipient_actor_id=candidate.recipient_actor_id,
                preference_id=candidate.preference_id,
                channel="LINE",
                status="PENDING",
                scheduled_at=scheduled_at,
                attempt_count=0,
                idempotency_key=idempotency_key,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
        )
        delivery = await self._session.scalar(
            select(NotificationDelivery)
            .where(NotificationDelivery.idempotency_key == idempotency_key)
            .with_for_update()
        )
        if delivery is None:
            return DeliveryClaim(notification_id, "SKIPPED", "DELIVERY_CLAIM_UNAVAILABLE")
        if delivery.status in {"SENT", "DELIVERED", "OPENED"}:
            return DeliveryClaim(delivery.notification_id, "REPLAYED", "ALREADY_SENT")
        if delivery.attempt_count >= max_attempts:
            delivery.status = "FAILED"
            delivery.last_error = "ATTEMPT_LIMIT_REACHED"
            return DeliveryClaim(delivery.notification_id, "FAILED", delivery.last_error)
        if delivery.status == "SENDING" and delivery.updated_at > now - _SENDING_STALE_AFTER:
            return DeliveryClaim(delivery.notification_id, "SKIPPED", "DELIVERY_IN_PROGRESS")
        if delivery.status == "CANCELLED":
            return DeliveryClaim(delivery.notification_id, "SKIPPED", "DELIVERY_CANCELLED")
        delivery.status = "SENDING"
        delivery.attempt_count += 1
        delivery.last_error = None
        await self._session.flush()
        return DeliveryClaim(delivery.notification_id, "CLAIMED")

    async def mark_sent(self, notification_id: UUID, *, now: datetime) -> None:
        delivery = await self._session.get(NotificationDelivery, notification_id)
        if delivery is not None and delivery.status == "SENDING":
            delivery.status = "SENT"
            delivery.sent_at = now
            delivery.last_error = None

    async def mark_failed(
        self,
        notification_id: UUID,
        *,
        reason_code: str,
        terminal: bool = False,
    ) -> None:
        delivery = await self._session.get(NotificationDelivery, notification_id)
        if delivery is not None and delivery.status == "SENDING":
            delivery.status = "FAILED"
            delivery.last_error = reason_code[:80]
            if terminal:
                delivery.attempt_count = max(delivery.attempt_count, 3)
