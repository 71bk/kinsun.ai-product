"""ELDER/FAMILY LINE account-linking lifecycle and live identity resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainException, NotFoundError
from app.events.outbox_writer import write_outbox_entry
from app.middleware.auth import ActorContext
from app.models.actor import Actor
from app.models.elder import Elder
from app.models.line_identity import ExternalIdentity, LineLinkChallenge
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant
from app.repositories.line_identity_repo import LineIdentityRepository
from app.schemas.line_identity import (
    LineLinkChallengeCreatedResponse,
    LineLinkChallengeStatusResponse,
    LineLinkStatusResponse,
    LineUnlinkResponse,
)
from app.services.authorization_service import authorize_elder
from app.services.line_identity_codec import LineIdentityCodec
from app.services.line_subject_cipher import LineSubjectCipher

_LINE_ACCOUNT_LINK_URL = "https://access.line.me/dialog/bot/accountLink"


@dataclass(frozen=True)
class ResolvedLineActor:
    actor_context: ActorContext
    elder: Elder


@dataclass(frozen=True)
class ResolvedLinkableActor:
    actor_context: ActorContext
    actor: Actor
    elder: Elder | None


class LineAccountLinkService:
    """Keep external identity mapping separate from live authorization state."""

    def __init__(
        self,
        session: AsyncSession,
        codec: LineIdentityCodec,
        *,
        challenge_ttl_seconds: int,
        challenge_max_attempts: int,
        frontend_base_url: str,
        subject_cipher: LineSubjectCipher | None = None,
    ) -> None:
        self._session = session
        self._codec = codec
        self._challenge_ttl_seconds = challenge_ttl_seconds
        self._challenge_max_attempts = challenge_max_attempts
        self._frontend_base_url = frontend_base_url.rstrip("/")
        self._subject_cipher = subject_cipher
        self._repository = LineIdentityRepository(session)

    async def get_status(self, actor: ActorContext) -> LineLinkStatusResponse:
        await self._require_linkable_actor(actor)
        identity = await self._repository.get_active_identity_for_actor(actor.actor_id)
        if identity is None:
            return LineLinkStatusResponse(
                linked=False,
                status="UNLINKED",
                linked_at=None,
                can_unlink=False,
            )
        return LineLinkStatusResponse(
            linked=True,
            status="ACTIVE",
            linked_at=identity.linked_at,
            can_unlink=True,
        )

    async def create_challenge(
        self,
        *,
        actor: ActorContext,
        link_token: str,
    ) -> LineLinkChallengeCreatedResponse:
        # Every challenge mutation uses actor -> subject -> challenge-row lock order.
        await self._acquire_actor_lock(actor.actor_id)
        resolved = await self._require_linkable_actor(actor)
        if await self._repository.get_active_identity_for_actor(actor.actor_id) is not None:
            raise ConflictError("LINE account is already linked")

        now = datetime.now(UTC)
        await self._repository.revoke_pending_challenges(
            actor_id=actor.actor_id,
            tenant_id=actor.tenant_id,
            now=now,
        )
        nonce, nonce_digest = self._codec.generate_nonce()
        challenge = LineLinkChallenge(
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            elder_id=resolved.elder.id if resolved.elder is not None else None,
            nonce_digest=nonce_digest,
            status="PENDING",
            expires_at=now + timedelta(seconds=self._challenge_ttl_seconds),
            attempt_count=0,
            max_attempts=self._challenge_max_attempts,
        )
        self._repository.add_challenge(challenge)
        await self._session.flush()
        query = urlencode({"linkToken": link_token, "nonce": nonce})
        account_link_url = f"{_LINE_ACCOUNT_LINK_URL}?{query}"
        return LineLinkChallengeCreatedResponse(
            challenge_id=challenge.id,
            expires_at=challenge.expires_at,
            account_link_url=account_link_url,
        )

    async def get_challenge_status(
        self,
        *,
        actor: ActorContext,
        challenge_id: UUID,
    ) -> LineLinkChallengeStatusResponse:
        await self._require_linkable_actor(actor)
        challenge = await self._repository.get_challenge_for_actor(
            challenge_id=challenge_id,
            actor_id=actor.actor_id,
            tenant_id=actor.tenant_id,
            for_update=True,
        )
        if challenge is None:
            raise NotFoundError("Resource not found")
        if challenge.status == "PENDING" and datetime.now(UTC) >= challenge.expires_at:
            challenge.status = "EXPIRED"
            challenge.version += 1
            await self._session.flush()
        return LineLinkChallengeStatusResponse(
            challenge_id=challenge.id,
            status=challenge.status,
            expires_at=challenge.expires_at,
            redeemed_at=challenge.redeemed_at,
        )

    async def unlink(
        self,
        *,
        actor: ActorContext,
        trace_id: str,
    ) -> LineUnlinkResponse:
        await self._acquire_actor_lock(actor.actor_id)
        resolved = await self._require_linkable_actor(actor)
        now = datetime.now(UTC)
        identity = await self._repository.get_active_identity_for_actor(
            actor.actor_id,
            for_update=True,
        )
        await self._repository.revoke_pending_challenges(
            actor_id=actor.actor_id,
            tenant_id=actor.tenant_id,
            now=now,
        )
        if identity is None:
            return LineUnlinkResponse()
        identity.status = "REVOKED"
        identity.revoked_at = now
        identity.version += 1
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="external_identity.revoked.v1",
            aggregate_type="external_identity",
            aggregate_id=identity.id,
            aggregate_version=identity.version,
            tenant_id=actor.tenant_id,
            elder_id=resolved.elder.id if resolved.elder is not None else None,
            actor_id=actor.actor_id,
            payload={
                "external_identity_id": str(identity.id),
                "provider": "LINE",
                "status": "REVOKED",
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=f"line-unlink:{identity.id}:{identity.version}",
        )
        return LineUnlinkResponse()

    async def redeem_account_link(
        self,
        *,
        nonce: str,
        line_user_id: str,
        result: str,
        trace_id: str,
        idempotency_key: str,
    ) -> bool:
        try:
            nonce_digest = self._codec.digest_nonce(nonce)
        except ValueError:
            return False

        # Read only enough to establish the global advisory-lock order. State is
        # re-read FOR UPDATE after acquiring those locks.
        challenge_hint = await self._repository.get_challenge_by_nonce(nonce_digest)
        if challenge_hint is None:
            return False
        try:
            subject_digest = self._codec.digest_subject(line_user_id) if result == "ok" else None
        except ValueError:
            subject_digest = None

        await self._acquire_actor_lock(challenge_hint.actor_id)
        if subject_digest is not None:
            await self._acquire_subject_lock(subject_digest)
        challenge = await self._repository.get_challenge_by_nonce(
            nonce_digest,
            for_update=True,
        )
        if challenge is None or challenge.actor_id != challenge_hint.actor_id:
            return False

        if challenge.status == "REDEEMED":
            if result != "ok" or subject_digest is None:
                return False
            identity = await self._session.get(
                ExternalIdentity,
                challenge.redeemed_external_identity_id,
            )
            return bool(
                identity is not None
                and identity.status == "ACTIVE"
                and identity.external_subject_digest == subject_digest
                and identity.digest_key_version == self._codec.key_version
            )
        if challenge.status != "PENDING":
            return False

        now = datetime.now(UTC)
        if now >= challenge.expires_at:
            challenge.status = "EXPIRED"
            challenge.version += 1
            await self._session.flush()
            return False
        if challenge.attempt_count >= challenge.max_attempts:
            await self._fail_challenge(challenge)
            return False

        challenge.attempt_count += 1
        if result != "ok" or subject_digest is None:
            await self._record_failed_attempt(challenge)
            return False

        resolved = await self._load_challenge_actor(challenge)
        if resolved is None:
            await self._record_failed_attempt(challenge)
            return False
        if resolved.elder is not None:
            try:
                await authorize_elder(
                    self._session,
                    resolved.actor_context,
                    resolved.elder.id,
                    "voice_session:create",
                )
            except DomainException:
                await self._record_failed_attempt(challenge)
                return False

        subject_identity = await self._repository.get_active_identity_by_subject(
            subject_digest=subject_digest,
            digest_key_version=self._codec.key_version,
            for_update=True,
        )
        actor_identity = await self._repository.get_active_identity_for_actor(
            challenge.actor_id,
            for_update=True,
        )
        if subject_identity is not None and subject_identity.actor_id != challenge.actor_id:
            await self._record_failed_attempt(challenge)
            return False
        if actor_identity is not None and (
            actor_identity.external_subject_digest != subject_digest
            or actor_identity.digest_key_version != self._codec.key_version
        ):
            await self._record_failed_attempt(challenge)
            return False

        identity = subject_identity or actor_identity
        if identity is None:
            identity = ExternalIdentity(
                provider="LINE",
                external_subject_digest=subject_digest,
                digest_key_version=self._codec.key_version,
                actor_id=challenge.actor_id,
                status="ACTIVE",
                linked_at=now,
                last_seen_at=now,
                encrypted_external_subject=(
                    self._subject_cipher.encrypt(line_user_id)
                    if self._subject_cipher is not None
                    else None
                ),
            )
            self._repository.add_identity(identity)
            await self._session.flush()
        else:
            identity.last_seen_at = now
            if self._subject_cipher is not None:
                identity.encrypted_external_subject = self._subject_cipher.encrypt(line_user_id)

        challenge.status = "REDEEMED"
        challenge.redeemed_external_identity_id = identity.id
        challenge.redeemed_at = now
        challenge.version += 1
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="external_identity.linked.v1",
            aggregate_type="external_identity",
            aggregate_id=identity.id,
            aggregate_version=identity.version,
            tenant_id=challenge.tenant_id,
            elder_id=challenge.elder_id,
            actor_id=challenge.actor_id,
            payload={
                "external_identity_id": str(identity.id),
                "provider": "LINE",
                "status": "ACTIVE",
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return True

    async def resolve_line_actor(self, line_user_id: str) -> ResolvedLineActor | None:
        try:
            subject_digest = self._codec.digest_subject(line_user_id)
        except ValueError:
            return None
        identity = await self._repository.get_active_identity_by_subject(
            subject_digest=subject_digest,
            digest_key_version=self._codec.key_version,
        )
        if identity is None:
            return None
        resolved = await self._load_live_elder_actor(actor_id=identity.actor_id)
        if resolved is None:
            return None
        try:
            await authorize_elder(
                self._session,
                resolved.actor_context,
                resolved.elder.id,
                "voice_session:create",
            )
        except DomainException:
            return None
        identity.last_seen_at = datetime.now(UTC)
        if self._subject_cipher is not None and identity.encrypted_external_subject is None:
            identity.encrypted_external_subject = self._subject_cipher.encrypt(line_user_id)
        return resolved

    async def resolve_linked_actor_type(self, line_user_id: str) -> str | None:
        """Return a linked active actor type without exposing any domain data."""
        try:
            subject_digest = self._codec.digest_subject(line_user_id)
        except ValueError:
            return None
        identity = await self._repository.get_active_identity_by_subject(
            subject_digest=subject_digest,
            digest_key_version=self._codec.key_version,
        )
        if identity is None:
            return None
        actor = await self._session.get(Actor, identity.actor_id)
        if actor is None or actor.status != "ACTIVE":
            return None
        identity.last_seen_at = datetime.now(UTC)
        if self._subject_cipher is not None and identity.encrypted_external_subject is None:
            identity.encrypted_external_subject = self._subject_cipher.encrypt(line_user_id)
        return actor.actor_type

    def build_frontend_start_url(self, link_token: str) -> str:
        return (
            f"{self._frontend_base_url}/backend/line/account-link/start?"
            f"{urlencode({'linkToken': link_token})}"
        )

    async def _require_elder_self(self, actor: ActorContext) -> Elder:
        if actor.actor_role != "ELDER" or actor.status != "ACTIVE":
            raise NotFoundError("Resource not found")
        resolved = await self._load_live_elder_actor(
            actor_id=actor.actor_id,
            expected_tenant_id=actor.tenant_id,
        )
        if resolved is None:
            raise NotFoundError("Resource not found")
        return resolved.elder

    async def _require_linkable_actor(self, actor: ActorContext) -> ResolvedLinkableActor:
        resolved = await self._load_live_linkable_actor(
            actor_id=actor.actor_id,
            expected_tenant_id=actor.tenant_id,
            expected_role=actor.actor_role,
        )
        if resolved is None or actor.status != "ACTIVE":
            raise NotFoundError("Resource not found")
        return resolved

    async def _load_challenge_actor(
        self,
        challenge: LineLinkChallenge,
    ) -> ResolvedLinkableActor | None:
        resolved = await self._load_live_linkable_actor(
            actor_id=challenge.actor_id,
            expected_tenant_id=challenge.tenant_id,
        )
        if resolved is None:
            return None
        if challenge.elder_id is not None and (
            resolved.elder is None or resolved.elder.id != challenge.elder_id
        ):
            return None
        if challenge.elder_id is None and resolved.elder is not None:
            return None
        return resolved

    async def _load_live_linkable_actor(
        self,
        *,
        actor_id: UUID,
        expected_tenant_id: UUID,
        expected_role: str | None = None,
    ) -> ResolvedLinkableActor | None:
        actor = await self._session.get(Actor, actor_id)
        if (
            actor is None
            or actor.status != "ACTIVE"
            or actor.actor_type not in {"ELDER", "FAMILY_MEMBER"}
            or (expected_role is not None and actor.actor_type != expected_role)
        ):
            return None
        if actor.actor_type == "ELDER":
            resolved_elder = await self._load_live_elder_actor(
                actor_id=actor_id,
                expected_tenant_id=expected_tenant_id,
            )
            if resolved_elder is None:
                return None
            return ResolvedLinkableActor(
                actor_context=resolved_elder.actor_context,
                actor=actor,
                elder=resolved_elder.elder,
            )

        now = datetime.now(UTC)
        membership = await self._session.scalar(
            select(ActorTenantMembership)
            .join(Tenant, Tenant.id == ActorTenantMembership.tenant_id)
            .where(
                ActorTenantMembership.actor_id == actor.id,
                ActorTenantMembership.tenant_id == expected_tenant_id,
                ActorTenantMembership.role_code == "FAMILY_MEMBER",
                ActorTenantMembership.care_unit_id.is_(None),
                ActorTenantMembership.status == "ACTIVE",
                ActorTenantMembership.effective_from <= now,
                or_(
                    ActorTenantMembership.effective_to.is_(None),
                    now < ActorTenantMembership.effective_to,
                ),
                Tenant.status == "ACTIVE",
            )
        )
        if membership is None:
            return None
        return ResolvedLinkableActor(
            actor_context=ActorContext(
                actor_id=actor.id,
                actor_role=actor.actor_type,
                tenant_id=expected_tenant_id,
                status=actor.status,
            ),
            actor=actor,
            elder=None,
        )

    async def _load_live_elder_actor(
        self,
        *,
        actor_id: UUID,
        expected_tenant_id: UUID | None = None,
        expected_elder_id: UUID | None = None,
    ) -> ResolvedLineActor | None:
        now = datetime.now(UTC)
        actor = await self._session.get(Actor, actor_id)
        if actor is None or actor.actor_type != "ELDER" or actor.status != "ACTIVE":
            return None

        elder_statement = select(Elder).where(
            Elder.actor_id == actor.id,
            Elder.status == "ACTIVE",
        )
        if expected_tenant_id is not None:
            elder_statement = elder_statement.where(Elder.tenant_id == expected_tenant_id)
        if expected_elder_id is not None:
            elder_statement = elder_statement.where(Elder.id == expected_elder_id)
        elder = await self._session.scalar(elder_statement)
        if elder is None:
            return None

        result = await self._session.execute(
            select(ActorTenantMembership)
            .join(Tenant, Tenant.id == ActorTenantMembership.tenant_id)
            .where(
                ActorTenantMembership.actor_id == actor.id,
                ActorTenantMembership.role_code == actor.actor_type,
                ActorTenantMembership.care_unit_id.is_(None),
                ActorTenantMembership.status == "ACTIVE",
                ActorTenantMembership.effective_from <= now,
                or_(
                    ActorTenantMembership.effective_to.is_(None),
                    now < ActorTenantMembership.effective_to,
                ),
                Tenant.status == "ACTIVE",
            )
        )
        memberships = list(result.scalars().all())
        if len(memberships) != 1 or memberships[0].tenant_id != elder.tenant_id:
            return None

        return ResolvedLineActor(
            actor_context=ActorContext(
                actor_id=actor.id,
                actor_role=actor.actor_type,
                tenant_id=memberships[0].tenant_id,
                status=actor.status,
            ),
            elder=elder,
        )

    async def _acquire_actor_lock(self, actor_id: UUID) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"line-actor:{actor_id}"},
        )

    async def _acquire_subject_lock(self, subject_digest: str) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": (f"line-subject:{self._codec.key_version}:{subject_digest}")},
        )

    async def _record_failed_attempt(self, challenge: LineLinkChallenge) -> None:
        if challenge.attempt_count >= challenge.max_attempts:
            await self._fail_challenge(challenge)
        else:
            await self._session.flush()

    async def _fail_challenge(self, challenge: LineLinkChallenge) -> None:
        if challenge.status == "PENDING":
            challenge.status = "FAILED"
            challenge.version += 1
            await self._session.flush()
