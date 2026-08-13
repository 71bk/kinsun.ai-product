"""Consume a verified pending Google identity into Core-owned account state."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError, ValidationError
from app.events.outbox_writer import write_outbox_entry
from app.models.actor import Actor
from app.models.elder import Elder
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.pending_identity import PendingExternalIdentity
from app.models.tenant import Tenant
from app.repositories.google_identity_repo import GoogleIdentityRepository
from app.services.app_session_service import AppSessionService, IssuedAppSession
from app.services.family_invitation_service import FamilyInvitationService
from app.services.pending_identity_tokens import PendingIdentityTokenCodec

_AUTHENTICATION_REQUIRED = "Authentication required"


@dataclass(frozen=True)
class CompletedGoogleOnboarding:
    intent: Literal["ELDER", "FAMILY"]
    actor_id: UUID
    tenant_id: UUID
    elder_id: UUID
    status: Literal["ACTIVE", "REDEEMED"]
    session: IssuedAppSession


class PendingGoogleOnboardingService:
    """Create formal Core state without ever auto-linking by e-mail address.

    The compatibility name is retained while ``provider`` selects either of
    the two approved direct OIDC providers.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        app_session_service: AppSessionService,
        family_invitation_service: FamilyInvitationService,
        repository: GoogleIdentityRepository | None = None,
        token_codec: PendingIdentityTokenCodec | None = None,
        clock: Callable[[], datetime] | None = None,
        provider: Literal["GOOGLE", "LINE"] = "GOOGLE",
    ) -> None:
        self._session = session
        self._provider = provider
        self._app_sessions = app_session_service
        self._family_invitations = family_invitation_service
        self._repository = repository or GoogleIdentityRepository(session, provider=provider)
        self._token_codec = token_codec or PendingIdentityTokenCodec()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def complete(
        self,
        *,
        pending_token: str,
        invitation_code: str | None,
        display_name: str | None,
        trace_id: str,
        idempotency_key: str,
    ) -> CompletedGoogleOnboarding:
        try:
            token_digest = self._token_codec.digest(pending_token)
        except ValueError:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None

        pending = await self._repository.get_pending_by_token_digest(
            token_digest,
            for_update=True,
        )
        now = self._clock()
        if (
            pending is None
            or pending.provider != self._provider
            or pending.status != "PENDING"
            or pending.expires_at <= now
            or pending.intent not in {"ELDER", "FAMILY"}
        ):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        await self._repository.acquire_subject_lock(
            subject_digest=pending.external_subject_digest,
            key_version=pending.digest_key_version,
        )
        identities = await self._repository.list_identities_by_subject(
            subject_digest=pending.external_subject_digest,
            key_version=pending.digest_key_version,
            for_update=True,
        )
        if identities:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        if pending.intent == "ELDER":
            if invitation_code is not None:
                raise ValidationError(
                    details=[
                        {
                            "field": "invitation_code",
                            "reason": "invitation_code is only valid for FAMILY onboarding",
                        }
                    ]
                )
            actor, tenant, elder, external_identity = await self._create_elder(
                pending=pending,
                requested_display_name=display_name,
                now=now,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
            )
            tenant_id = tenant.id
            elder_id = elder.id
            status: Literal["ACTIVE", "REDEEMED"] = "ACTIVE"
        else:
            if invitation_code is None:
                raise ValidationError(
                    details=[
                        {
                            "field": "invitation_code",
                            "reason": "invitation_code is required for FAMILY onboarding",
                        }
                    ]
                )
            (
                redeemed,
                external_identity,
            ) = await self._family_invitations.redeem_pending_external_identity(
                pending=pending,
                invitation_code=invitation_code,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
            )
            actor = await self._session.get(Actor, redeemed.actor_id)
            if actor is None:
                raise AuthenticationError(_AUTHENTICATION_REQUIRED)
            tenant_id = redeemed.tenant_id
            elder_id = redeemed.elder_id
            status = "REDEEMED"

        pending.status = "CONSUMED"
        pending.consumed_at = now
        pending.version = (pending.version or 0) + 1
        await self._repository.flush()
        issued_session = await self._app_sessions.issue(external_identity_id=external_identity.id)

        return CompletedGoogleOnboarding(
            intent=pending.intent,
            actor_id=actor.id,
            tenant_id=tenant_id,
            elder_id=elder_id,
            status=status,
            session=issued_session,
        )

    async def _create_elder(
        self,
        *,
        pending: PendingExternalIdentity,
        requested_display_name: str | None,
        now: datetime,
        trace_id: str,
        idempotency_key: str,
    ) -> tuple[Actor, Tenant, Elder, ExternalIdentity]:
        email = pending.verified_email.strip().casefold() if pending.verified_email else None
        if email is not None:
            # Hash the lock input so no e-mail address appears in database
            # diagnostics while concurrent first-use checks remain serialized.
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

        normalized_name = requested_display_name.strip() if requested_display_name else ""
        fallback_name = pending.display_name or (email.partition("@")[0] if email else None)
        display_name = (normalized_name or fallback_name or "使用者")[:120]
        tenant = Tenant(
            tenant_type="HOUSEHOLD",
            name=f"{display_name} 的家庭"[:160],
            status="ACTIVE",
            timezone="Asia/Taipei",
        )
        actor = Actor(
            actor_type="ELDER",
            display_name=display_name,
            email=email,
            status="ACTIVE",
        )
        self._session.add_all((tenant, actor))
        await self._session.flush()
        elder = Elder(
            tenant_id=tenant.id,
            actor_id=actor.id,
            display_name=display_name,
            primary_care_setting="INDEPENDENT",
            status="ACTIVE",
            preferred_language="ZH_TW",
            response_length_preference="SHORT",
            timezone="Asia/Taipei",
        )
        membership = ActorTenantMembership(
            actor_id=actor.id,
            tenant_id=tenant.id,
            care_unit_id=None,
            role_code="ELDER",
            status="ACTIVE",
            effective_from=now,
        )
        external_identity = ExternalIdentity(
            provider=pending.provider,
            external_subject_digest=pending.external_subject_digest,
            digest_key_version=pending.digest_key_version,
            actor_id=actor.id,
            status="ACTIVE",
            version=1,
        )
        self._session.add_all((elder, membership, external_identity))
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="elder.onboarded.v1",
            aggregate_type="elder",
            aggregate_id=elder.id,
            tenant_id=tenant.id,
            elder_id=elder.id,
            actor_id=actor.id,
            payload={
                "elder_id": str(elder.id),
                "actor_id": str(actor.id),
                "tenant_id": str(tenant.id),
                "registration_status": "ACTIVE",
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
            tenant_id=tenant.id,
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
        return actor, tenant, elder, external_identity
