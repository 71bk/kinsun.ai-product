"""Persistence boundary for direct identity linking and safe consolidation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import literal, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as registered_models  # noqa: F401 - populate SQLAlchemy metadata
from app.db.base import Base
from app.models.account_merge import AccountMergeRequest
from app.models.actor import Actor
from app.models.app_session import AppSession
from app.models.elder import Elder
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.outbox import OutboxEvent
from app.models.tenant import Tenant
from app.repositories.app_session_repo import ResolvedAppSession


@dataclass(frozen=True)
class EmptyElderAccountSkeleton:
    actor: Actor
    identity: ExternalIdentity
    tenant: Tenant
    membership: ActorTenantMembership
    elder: Elder


class AccountIdentityRepository:
    """Serialize actor/identity changes and conservatively detect domain data."""

    _SKELETON_TABLES = frozenset(
        {
            "account_merge_request",
            "actor",
            "actor_tenant_membership",
            "app_session",
            "elder",
            "external_identity",
            "outbox_event",
            "pending_external_identity",
            "tenant",
        }
    )
    _ONBOARDING_EVENT_TYPES = frozenset({"elder.onboarded.v1", "external_identity.linked.v1"})

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire_subject_lock(self, *, subject_digest: str, key_version: int) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"line-subject:v{key_version}:{subject_digest}"},
        )

    async def lock_actors(self, *actor_ids: UUID) -> dict[UUID, Actor]:
        ordered_ids = sorted(set(actor_ids), key=str)
        result = await self._session.scalars(
            select(Actor).where(Actor.id.in_(ordered_ids)).order_by(Actor.id).with_for_update()
        )
        return {actor.id: actor for actor in result.all()}

    async def get_app_session(
        self,
        token_digest: str,
        *,
        for_update: bool = False,
    ) -> ResolvedAppSession | None:
        statement = (
            select(AppSession, ExternalIdentity, Actor)
            .join(ExternalIdentity, ExternalIdentity.id == AppSession.external_identity_id)
            .join(Actor, Actor.id == AppSession.actor_id)
            .where(AppSession.token_digest == token_digest)
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        app_session, identity, actor = row
        return ResolvedAppSession(
            app_session=app_session,
            identity=identity,
            actor=actor,
        )

    async def list_active_identities(
        self,
        *,
        actor_id: UUID,
        for_update: bool = False,
    ) -> list[ExternalIdentity]:
        statement = (
            select(ExternalIdentity)
            .where(
                ExternalIdentity.actor_id == actor_id,
                ExternalIdentity.status == "ACTIVE",
            )
            .order_by(ExternalIdentity.provider, ExternalIdentity.id)
        )
        if for_update:
            statement = statement.with_for_update()
        return list((await self._session.scalars(statement)).all())

    async def list_identities_by_subject(
        self,
        *,
        subject_digest: str,
        key_version: int,
        for_update: bool = False,
    ) -> list[ExternalIdentity]:
        statement = (
            select(ExternalIdentity)
            .where(
                ExternalIdentity.provider == "LINE",
                ExternalIdentity.external_subject_digest == subject_digest,
                ExternalIdentity.digest_key_version == key_version,
            )
            .order_by(ExternalIdentity.created_at, ExternalIdentity.id)
        )
        if for_update:
            statement = statement.with_for_update()
        return list((await self._session.scalars(statement)).all())

    async def get_identity(
        self,
        identity_id: UUID,
        *,
        for_update: bool = False,
    ) -> ExternalIdentity | None:
        statement = select(ExternalIdentity).where(ExternalIdentity.id == identity_id)
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def get_open_merge(
        self,
        *,
        source_actor_id: UUID,
        target_actor_id: UUID,
        for_update: bool = False,
    ) -> AccountMergeRequest | None:
        statement = select(AccountMergeRequest).where(
            AccountMergeRequest.source_actor_id == source_actor_id,
            AccountMergeRequest.target_actor_id == target_actor_id,
            AccountMergeRequest.status.in_({"PENDING_CONFIRMATION", "PENDING_REVIEW"}),
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def get_merge_by_token_digest(
        self,
        token_digest: str,
        *,
        for_update: bool = False,
    ) -> AccountMergeRequest | None:
        statement = select(AccountMergeRequest).where(
            AccountMergeRequest.token_digest == token_digest
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def empty_elder_skeleton(
        self,
        *,
        source_actor_id: UUID,
        source_identity_id: UUID,
    ) -> EmptyElderAccountSkeleton | None:
        actor = await self._session.scalar(
            select(Actor).where(Actor.id == source_actor_id).with_for_update()
        )
        identity = await self._session.scalar(
            select(ExternalIdentity)
            .where(ExternalIdentity.id == source_identity_id)
            .with_for_update()
        )
        if (
            actor is None
            or actor.status != "ACTIVE"
            or actor.actor_type != "ELDER"
            or identity is None
            or identity.actor_id != actor.id
            or identity.provider != "LINE"
            or identity.status != "ACTIVE"
            # A stored push-delivery subject means this identity has already
            # crossed into the Messaging API domain.  The bounded Login-only
            # consolidation flow must never revoke or move that destination.
            or identity.encrypted_external_subject is not None
        ):
            return None

        identities = list(
            (
                await self._session.scalars(
                    select(ExternalIdentity)
                    .where(ExternalIdentity.actor_id == actor.id)
                    .with_for_update()
                )
            ).all()
        )
        memberships = list(
            (
                await self._session.scalars(
                    select(ActorTenantMembership)
                    .where(ActorTenantMembership.actor_id == actor.id)
                    .with_for_update()
                )
            ).all()
        )
        elders = list(
            (
                await self._session.scalars(
                    select(Elder).where(Elder.actor_id == actor.id).with_for_update()
                )
            ).all()
        )
        if len(identities) != 1 or len(memberships) != 1 or len(elders) != 1:
            return None
        membership = memberships[0]
        elder = elders[0]
        tenant = await self._session.scalar(
            select(Tenant).where(Tenant.id == membership.tenant_id).with_for_update()
        )
        if (
            membership.status != "ACTIVE"
            or membership.role_code != "ELDER"
            or membership.care_unit_id is not None
            or membership.effective_to is not None
            or elder.tenant_id != membership.tenant_id
            or elder.status != "ACTIVE"
            or tenant is None
            or tenant.tenant_type != "HOUSEHOLD"
            or tenant.status != "ACTIVE"
        ):
            return None

        tenant_memberships = list(
            (
                await self._session.scalars(
                    select(ActorTenantMembership).where(
                        ActorTenantMembership.tenant_id == tenant.id
                    )
                )
            ).all()
        )
        tenant_elders = list(
            (await self._session.scalars(select(Elder).where(Elder.tenant_id == tenant.id))).all()
        )
        if tenant_memberships != [membership] or tenant_elders != [elder]:
            return None
        if await self._has_non_skeleton_data(
            actor_id=actor.id,
            tenant_id=tenant.id,
            elder_id=elder.id,
        ):
            return None
        return EmptyElderAccountSkeleton(
            actor=actor,
            identity=identity,
            tenant=tenant,
            membership=membership,
            elder=elder,
        )

    async def _has_non_skeleton_data(
        self,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        elder_id: UUID,
    ) -> bool:
        unsafe_outbox = await self._session.scalar(
            select(literal(True))
            .select_from(OutboxEvent)
            .where(
                or_(
                    OutboxEvent.actor_id == actor_id,
                    OutboxEvent.tenant_id == tenant_id,
                    OutboxEvent.elder_id == elder_id,
                ),
                OutboxEvent.event_type.not_in(self._ONBOARDING_EVENT_TYPES),
            )
            .limit(1)
        )
        if unsafe_outbox:
            return True

        for table in Base.metadata.sorted_tables:
            if table.name in self._SKELETON_TABLES:
                continue
            conditions: list[sa.ColumnElement[bool]] = []
            if "tenant_id" in table.c:
                conditions.append(table.c.tenant_id == tenant_id)
            if "elder_id" in table.c:
                conditions.append(table.c.elder_id == elder_id)
            for column in table.c:
                if column.name.endswith("_actor_id"):
                    conditions.append(column == actor_id)
            if not conditions:
                continue
            found = await self._session.scalar(
                select(literal(True)).select_from(table).where(or_(*conditions)).limit(1)
            )
            if found:
                return True
        return False

    async def revoke_active_sessions(self, *, actor_ids: set[UUID], now: datetime) -> None:
        await self._session.execute(
            update(AppSession)
            .where(AppSession.actor_id.in_(actor_ids), AppSession.status == "ACTIVE")
            .values(
                status="REVOKED",
                revoked_at=now,
                version=AppSession.version + 1,
            )
        )

    def add_identity(self, identity: ExternalIdentity) -> None:
        self._session.add(identity)

    def add_merge(self, merge: AccountMergeRequest) -> None:
        self._session.add(merge)

    async def flush(self) -> None:
        await self._session.flush()
