"""Tenant/actor-scoped persistence for family-owned notification settings."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.elder import Elder
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.notification import NotificationPreference
from app.models.report import FamilyRelationship
from app.models.tenant import Tenant


class FamilyNotificationPreferenceRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID, actor_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._actor_id = actor_id

    async def has_daily_relationship(self, elder_id: UUID, consent_id: UUID, now: datetime) -> bool:
        relationship_id = await self._session.scalar(
            select(FamilyRelationship.id)
            .join(Elder, Elder.id == FamilyRelationship.elder_id)
            .join(Tenant, Tenant.id == Elder.tenant_id)
            .join(Actor, Actor.id == FamilyRelationship.family_actor_id)
            .where(
                Elder.id == elder_id,
                Elder.tenant_id == self._tenant_id,
                Elder.status == "ACTIVE",
                Tenant.status == "ACTIVE",
                Actor.status == "ACTIVE",
                Actor.actor_type == "FAMILY_MEMBER",
                select(ActorTenantMembership.id)
                .where(
                    ActorTenantMembership.actor_id == self._actor_id,
                    ActorTenantMembership.tenant_id == self._tenant_id,
                    ActorTenantMembership.role_code == "FAMILY_MEMBER",
                    ActorTenantMembership.care_unit_id.is_(None),
                    ActorTenantMembership.status == "ACTIVE",
                    ActorTenantMembership.effective_from <= now,
                    or_(
                        ActorTenantMembership.effective_to.is_(None),
                        now < ActorTenantMembership.effective_to,
                    ),
                )
                .exists(),
                FamilyRelationship.family_actor_id == self._actor_id,
                FamilyRelationship.status == "ACTIVE",
                FamilyRelationship.consent_id == consent_id,
                FamilyRelationship.effective_from <= now,
                or_(
                    FamilyRelationship.effective_to.is_(None), now < FamilyRelationship.effective_to
                ),
                or_(
                    FamilyRelationship.share_scope.any("REPORT_DAILY"),
                    FamilyRelationship.share_scope.any("REPORT_ALL"),
                ),
            )
        )
        return relationship_id is not None

    async def get_for_actor(
        self, elder_id: UUID, *, lock: bool = False
    ) -> NotificationPreference | None:
        statement = (
            select(NotificationPreference)
            .where(
                NotificationPreference.elder_id == elder_id,
                NotificationPreference.family_actor_id == self._actor_id,
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def active_line_identity(self) -> ExternalIdentity | None:
        return await self._session.scalar(
            select(ExternalIdentity)
            .where(
                ExternalIdentity.actor_id == self._actor_id,
                ExternalIdentity.provider == "LINE",
                ExternalIdentity.status == "ACTIVE",
            )
            .execution_options(populate_existing=True)
        )

    async def lock_elder(self, elder_id: UUID) -> Elder | None:
        return await self._session.scalar(
            select(Elder)
            .where(Elder.id == elder_id, Elder.tenant_id == self._tenant_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def save(self, preference: NotificationPreference) -> None:
        self._session.add(preference)
        await self._session.flush()
