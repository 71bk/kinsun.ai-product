"""Consent-bound, one-time family invitation lifecycle."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import normalize_email_text
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.events.outbox_writer import write_outbox_entry
from app.models.actor import Actor
from app.models.care_relationship import CareRelationship
from app.models.elder import Elder
from app.models.family_invitation import FamilyInvitation
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.pending_identity import PendingExternalIdentity
from app.models.report import FamilyRelationship
from app.models.tenant import Tenant
from app.repositories.consent_repo import ConsentRepository
from app.repositories.family_invitation_repo import FamilyInvitationRepository
from app.schemas.family_invitation import (
    CreateFamilyInvitationRequest,
    FamilyInvitationCreatedResponse,
    FamilyInvitationListResponse,
    FamilyInvitationRedeemedResponse,
    FamilyInvitationStatusResponse,
)
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec

_AUTHENTICATION_REQUIRED = "Authentication required"
_FAMILY_REPORT_ACTIONS = ["family_report:read"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FamilyInvitationService:
    """Issue and redeem family access without deriving authorization from JWT claims."""

    def __init__(
        self,
        session: AsyncSession,
        codec: FamilyInvitationTokenCodec,
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._session = session
        self._codec = codec
        self._now = now
        self._invitations = FamilyInvitationRepository(session)

    async def create(
        self,
        *,
        tenant_id: UUID,
        elder_id: UUID,
        actor_id: UUID,
        actor_role: str,
        request: CreateFamilyInvitationRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> FamilyInvitationCreatedResponse:
        elder = await self._require_elder_self(
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        now = self._now()
        consent = await ConsentRepository(self._session, tenant_id).get_active(
            elder_id=elder.id,
            purpose_code="FAMILY_SHARING",
            current_time=now,
        )
        if consent is None:
            raise ConflictError(
                "Family sharing consent must be active before issuing an invitation"
            )
        consent_scopes = set((consent.scope or {}).get("share_scopes", []))
        if not set(request.share_scope).issubset(consent_scopes):
            raise ConflictError("Invitation scope exceeds the active family sharing consent")

        code, token_hash = self._codec.generate()
        invitee_email_hmac = (
            self._codec.hash_email(request.invitee_email) if request.invitee_email else None
        )
        invitation = FamilyInvitation(
            tenant_id=tenant_id,
            elder_id=elder_id,
            issued_by_actor_id=actor_id,
            invitee_email_hmac=invitee_email_hmac,
            token_hash=token_hash,
            share_scope=list(request.share_scope),
            consent_id=consent.id,
            status="ISSUED",
            expires_at=now + timedelta(hours=request.expires_in_hours),
            attempt_count=0,
            max_attempts=5,
        )
        self._invitations.add(invitation)
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="family.invitation.issued.v1",
            aggregate_type="family_invitation",
            aggregate_id=invitation.id,
            aggregate_version=invitation.version,
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose="FAMILY_SHARING",
            consent_version=consent.version,
            payload={
                "invitation_id": str(invitation.id),
                "elder_id": str(elder_id),
                "status": invitation.status,
                "expires_at": invitation.expires_at.isoformat(),
                "share_scope": list(invitation.share_scope),
                "recipient_bound": invitation.invitee_email_hmac is not None,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return FamilyInvitationCreatedResponse(
            invitation_id=invitation.id,
            invitation_code=code,
            share_scope=invitation.share_scope,
            expires_at=invitation.expires_at,
        )

    async def redeem_pending_external_identity(
        self,
        *,
        pending: PendingExternalIdentity,
        invitation_code: str,
        trace_id: str,
        idempotency_key: str,
    ) -> tuple[FamilyInvitationRedeemedResponse, ExternalIdentity]:
        """Redeem an invitation for a verified, not-yet-linked external identity.

        Pending identity consumption remains the caller's responsibility so
        account creation, invitation redemption, and App Session issuance can
        commit as one transaction.
        """
        now = self._now()
        if (
            pending.provider not in {"GOOGLE", "LINE"}
            or pending.intent != "FAMILY"
            or pending.status != "PENDING"
            or pending.expires_at <= now
        ):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        email = normalize_email_text(pending.verified_email) if pending.verified_email else None
        token_hash = self._codec.hash_code(invitation_code)
        invitation = await self._invitations.get_by_token_hash_for_update(token_hash)
        if invitation is None or invitation.status != "ISSUED" or now >= invitation.expires_at:
            self._invalid_invitation()
        if invitation.invitee_email_hmac is not None and (
            email is None
            or not self._codec.matches(
                invitation.invitee_email_hmac,
                self._codec.hash_email(email),
            )
        ):
            self._invalid_invitation()

        elder, consent = await self._require_live_invitation_authority(invitation, now)
        actor, external_identity = await self._create_external_family_actor(
            pending=pending,
            email=email,
        )
        membership = await self._ensure_single_household_membership(
            actor=actor,
            tenant_id=invitation.tenant_id,
            now=now,
        )
        relationship = await self._ensure_care_relationship(
            actor_id=actor.id,
            invitation=invitation,
            now=now,
        )
        family_relationship = await self._ensure_family_relationship(
            actor_id=actor.id,
            invitation=invitation,
            now=now,
        )

        invitation.status = "REDEEMED"
        invitation.redeemed_by_actor_id = actor.id
        invitation.redeemed_at = now
        invitation.version += 1
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="family.invitation.redeemed.v1",
            aggregate_type="family_invitation",
            aggregate_id=invitation.id,
            aggregate_version=invitation.version,
            tenant_id=invitation.tenant_id,
            elder_id=elder.id,
            actor_id=actor.id,
            purpose="FAMILY_SHARING",
            consent_version=consent.version,
            payload={
                "invitation_id": str(invitation.id),
                "elder_id": str(elder.id),
                "family_actor_id": str(actor.id),
                "membership_id": str(membership.id),
                "relationship_id": str(relationship.id),
                "family_relationship_id": str(family_relationship.id),
                "status": invitation.status,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        await write_outbox_entry(
            self._session,
            event_type="external_identity.linked.v1",
            aggregate_type="external_identity",
            aggregate_id=external_identity.id,
            aggregate_version=external_identity.version,
            tenant_id=invitation.tenant_id,
            elder_id=elder.id,
            actor_id=actor.id,
            purpose="AUTHENTICATION",
            payload={
                "external_identity_id": str(external_identity.id),
                "actor_id": str(actor.id),
                "provider": external_identity.provider,
                "status": external_identity.status,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=f"{idempotency_key}:external-identity",
        )
        return (
            FamilyInvitationRedeemedResponse(
                invitation_id=invitation.id,
                actor_id=actor.id,
                tenant_id=invitation.tenant_id,
                elder_id=invitation.elder_id,
                relationship_id=relationship.id,
                family_relationship_id=family_relationship.id,
            ),
            external_identity,
        )

    async def list_for_elder(
        self,
        *,
        tenant_id: UUID,
        elder_id: UUID,
        actor_id: UUID,
        actor_role: str,
    ) -> FamilyInvitationListResponse:
        await self._require_elder_self(
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        now = self._now()
        invitations = await self._invitations.list_for_elder(
            tenant_id=tenant_id,
            elder_id=elder_id,
        )
        return FamilyInvitationListResponse(
            items=[self._status_response(item, now) for item in invitations]
        )

    async def revoke(
        self,
        *,
        tenant_id: UUID,
        elder_id: UUID,
        invitation_id: UUID,
        actor_id: UUID,
        actor_role: str,
        trace_id: str,
        idempotency_key: str,
    ) -> FamilyInvitationStatusResponse:
        await self._require_elder_self(
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role=actor_role,
        )
        invitation = await self._invitations.get_for_elder(
            invitation_id=invitation_id,
            tenant_id=tenant_id,
            elder_id=elder_id,
            for_update=True,
        )
        if invitation is None:
            raise NotFoundError("Resource not found")
        now = self._now()
        if invitation.status == "REVOKED":
            return self._status_response(invitation, now)
        if invitation.status != "ISSUED" or now >= invitation.expires_at:
            raise ConflictError("Only an active invitation can be revoked")
        invitation.status = "REVOKED"
        invitation.revoked_at = now
        invitation.version += 1
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="family.invitation.revoked.v1",
            aggregate_type="family_invitation",
            aggregate_id=invitation.id,
            aggregate_version=invitation.version,
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose="FAMILY_SHARING",
            payload={
                "invitation_id": str(invitation.id),
                "elder_id": str(elder_id),
                "status": invitation.status,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return self._status_response(invitation, now)

    async def _require_elder_self(
        self,
        *,
        tenant_id: UUID,
        elder_id: UUID,
        actor_id: UUID,
        actor_role: str,
    ) -> Elder:
        if actor_role != "ELDER":
            raise NotFoundError("Resource not found")
        elder = await self._session.scalar(
            select(Elder).where(
                Elder.id == elder_id,
                Elder.tenant_id == tenant_id,
                Elder.actor_id == actor_id,
                Elder.status == "ACTIVE",
            )
        )
        if elder is None:
            raise NotFoundError("Resource not found")
        return elder

    async def _require_live_invitation_authority(
        self,
        invitation: FamilyInvitation,
        now: datetime,
    ):
        elder = await self._session.scalar(
            select(Elder)
            .join(Tenant, Tenant.id == Elder.tenant_id)
            .where(
                Elder.id == invitation.elder_id,
                Elder.tenant_id == invitation.tenant_id,
                Elder.status == "ACTIVE",
                Tenant.status == "ACTIVE",
                Tenant.tenant_type == "HOUSEHOLD",
            )
        )
        if elder is None or elder.actor_id != invitation.issued_by_actor_id:
            self._invalid_invitation()
        consent = await ConsentRepository(self._session, invitation.tenant_id).get_active(
            elder_id=invitation.elder_id,
            purpose_code="FAMILY_SHARING",
            current_time=now,
        )
        if consent is None or consent.id != invitation.consent_id:
            self._invalid_invitation()
        consent_scopes = set((consent.scope or {}).get("share_scopes", []))
        if not set(invitation.share_scope).issubset(consent_scopes):
            self._invalid_invitation()
        return elder, consent

    async def _create_external_family_actor(
        self,
        *,
        pending: PendingExternalIdentity,
        email: str | None,
    ) -> tuple[Actor, ExternalIdentity]:
        identities = list(
            (
                await self._session.execute(
                    select(ExternalIdentity).where(
                        ExternalIdentity.provider == pending.provider,
                        ExternalIdentity.external_subject_digest == pending.external_subject_digest,
                        ExternalIdentity.digest_key_version == pending.digest_key_version,
                    )
                )
            )
            .scalars()
            .all()
        )
        if identities:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        if email is not None:
            email_digest = hashlib.sha256(email.encode("utf-8")).hexdigest()
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": f"external-email:{email_digest}"},
            )
            email_owner = await self._session.scalar(
                select(Actor).where(func.lower(Actor.email) == email)
            )
            if email_owner is not None:
                raise ConflictError("This identity requires administrator review")

        display_name = pending.display_name or (email.partition("@")[0] if email else None)
        actor = Actor(
            actor_type="FAMILY_MEMBER",
            display_name=(display_name or "Family member")[:120],
            email=email,
            status="ACTIVE",
        )
        self._session.add(actor)
        await self._session.flush()
        external_identity = ExternalIdentity(
            provider=pending.provider,
            external_subject_digest=pending.external_subject_digest,
            digest_key_version=pending.digest_key_version,
            actor_id=actor.id,
            status="ACTIVE",
            version=1,
        )
        self._session.add(external_identity)
        await self._session.flush()
        return actor, external_identity

    async def _ensure_single_household_membership(
        self,
        *,
        actor: Actor,
        tenant_id: UUID,
        now: datetime,
    ) -> ActorTenantMembership:
        active_memberships = list(
            (
                await self._session.execute(
                    select(ActorTenantMembership).where(
                        ActorTenantMembership.actor_id == actor.id,
                        ActorTenantMembership.care_unit_id.is_(None),
                        ActorTenantMembership.status == "ACTIVE",
                        ActorTenantMembership.effective_from <= now,
                        or_(
                            ActorTenantMembership.effective_to.is_(None),
                            now < ActorTenantMembership.effective_to,
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        if active_memberships:
            if len(active_memberships) != 1:
                raise ConflictError("Family identity has ambiguous tenant membership")
            membership = active_memberships[0]
            if membership.tenant_id != tenant_id or membership.role_code != "FAMILY_MEMBER":
                raise ConflictError("Family identity already belongs to another household")
            return membership

        historical = await self._session.scalar(
            select(ActorTenantMembership).where(
                ActorTenantMembership.actor_id == actor.id,
                ActorTenantMembership.tenant_id == tenant_id,
                ActorTenantMembership.care_unit_id.is_(None),
                ActorTenantMembership.role_code == "FAMILY_MEMBER",
            )
        )
        if historical is not None:
            historical.status = "ACTIVE"
            historical.effective_from = now
            historical.effective_to = None
            await self._session.flush()
            return historical

        membership = ActorTenantMembership(
            actor_id=actor.id,
            tenant_id=tenant_id,
            care_unit_id=None,
            role_code="FAMILY_MEMBER",
            status="ACTIVE",
            effective_from=now,
        )
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def _ensure_care_relationship(
        self,
        *,
        actor_id: UUID,
        invitation: FamilyInvitation,
        now: datetime,
    ) -> CareRelationship:
        relationship = await self._session.scalar(
            select(CareRelationship)
            .where(
                CareRelationship.actor_id == actor_id,
                CareRelationship.elder_id == invitation.elder_id,
                CareRelationship.tenant_id == invitation.tenant_id,
                CareRelationship.relationship_type == "FAMILY_SHARE",
                CareRelationship.status == "ACTIVE",
                CareRelationship.effective_from <= now,
                or_(
                    CareRelationship.effective_to.is_(None),
                    now < CareRelationship.effective_to,
                ),
            )
            .order_by(CareRelationship.created_at.desc())
            .limit(1)
        )
        if relationship is not None:
            relationship.scope = list(_FAMILY_REPORT_ACTIONS)
            return relationship
        relationship = CareRelationship(
            actor_id=actor_id,
            elder_id=invitation.elder_id,
            tenant_id=invitation.tenant_id,
            care_unit_id=None,
            relationship_type="FAMILY_SHARE",
            scope=list(_FAMILY_REPORT_ACTIONS),
            status="ACTIVE",
            effective_from=now,
        )
        self._session.add(relationship)
        await self._session.flush()
        return relationship

    async def _ensure_family_relationship(
        self,
        *,
        actor_id: UUID,
        invitation: FamilyInvitation,
        now: datetime,
    ) -> FamilyRelationship:
        relationship = await self._session.scalar(
            select(FamilyRelationship).where(
                FamilyRelationship.elder_id == invitation.elder_id,
                FamilyRelationship.family_actor_id == actor_id,
                FamilyRelationship.consent_id == invitation.consent_id,
            )
        )
        if relationship is None:
            relationship = FamilyRelationship(
                elder_id=invitation.elder_id,
                family_actor_id=actor_id,
                share_scope=list(invitation.share_scope),
                status="ACTIVE",
                effective_from=now,
                consent_id=invitation.consent_id,
            )
            self._session.add(relationship)
            await self._session.flush()
            return relationship
        relationship.share_scope = list(invitation.share_scope)
        relationship.status = "ACTIVE"
        relationship.effective_from = now
        relationship.effective_to = None
        return relationship

    @staticmethod
    def _invalid_invitation() -> None:
        raise ValidationError(
            details=[
                {
                    "field": "invitation_code",
                    "reason": "Invitation code is unavailable",
                }
            ]
        )

    @staticmethod
    def _status_response(
        invitation: FamilyInvitation,
        now: datetime,
    ) -> FamilyInvitationStatusResponse:
        status = invitation.status
        if status == "ISSUED" and now >= invitation.expires_at:
            status = "EXPIRED"
        return FamilyInvitationStatusResponse(
            invitation_id=invitation.id,
            status=status,
            share_scope=invitation.share_scope,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )
