"""Development-only, administrator-issued workforce account activation."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.config import get_settings
from app.core.cursor import encode_cursor
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.events.outbox_writer import write_outbox_entry
from app.models.actor import Actor
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.password_credential import PasswordCredential
from app.models.staff_invitation import StaffInvitation
from app.repositories.kinsun_identity_repo import KinsunIdentityRepository
from app.repositories.staff_invitation_repo import StaffInvitationRepository
from app.schemas.staff_invitation import (
    AcceptStaffInvitationRequest,
    CreatedStaffInvitationResponse,
    CreateStaffInvitationRequest,
    StaffCareUnitListResponse,
    StaffCareUnitView,
    StaffInvitationListResponse,
    StaffInvitationView,
)
from app.services.actor_context_resolver import resolve_active_actor_context
from app.services.kinsun_identity_codec import KinsunIdentityCodec
from app.services.password_hasher import PasswordHasher

ROLE_UNITS = {
    "DAYCARE_CARE_WORKER": {"DAYCARE_CENTER", "COMMUNITY_SITE"},
    "HOME_CARE_WORKER": {"HOME_CARE_AGENCY"},
}


def require_staff_invitations() -> None:
    settings = get_settings()
    if (
        not settings.staff_invitations_enabled
        or settings.app_env != "development"
        or not settings.kinsun_native_auth_enabled
    ):
        raise NotFoundError("Resource not found")


def invitation_view(row: StaffInvitation) -> StaffInvitationView:
    return StaffInvitationView(
        invitation_id=row.id,
        display_name=row.display_name,
        role_code=row.role_code,
        care_unit_id=row.care_unit_id,
        status="EXPIRED"
        if row.status == "ISSUED" and row.expires_at <= datetime.now(UTC)
        else row.status,
        expires_at=row.expires_at,
        version=row.version,
    )


class StaffInvitationService:
    def __init__(
        self, session: AsyncSession, codec: KinsunIdentityCodec, password_hasher: PasswordHasher
    ) -> None:
        self.session = session
        self.codec = codec
        self.hasher = password_hasher
        self.identities = KinsunIdentityRepository(session)

    async def require_admin(self, context: ActorContext) -> StaffInvitationRepository:
        require_staff_invitations()
        if context.actor_role != "ADMIN" or context.status != "ACTIVE":
            raise NotFoundError("Resource not found")
        repo = StaffInvitationRepository(self.session, context.tenant_id)
        actor = await repo.actor(context.actor_id)
        if actor is None or actor.actor_type != "ADMIN":
            raise NotFoundError("Resource not found")
        try:
            live = await resolve_active_actor_context(self.session, actor)
        except AuthenticationError:
            raise NotFoundError("Resource not found") from None
        if live != context:
            raise NotFoundError("Resource not found")
        return repo

    async def list(
        self, actor: ActorContext, cursor: str | None, limit: int
    ) -> StaffInvitationListResponse:
        repo = await self.require_admin(actor)
        rows = await repo.list(cursor, limit)
        return StaffInvitationListResponse(
            items=[invitation_view(row) for row in rows[:limit]],
            next_cursor=encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id)
            if len(rows) > limit
            else None,
        )

    async def units(
        self, actor: ActorContext, cursor: str | None, limit: int
    ) -> StaffCareUnitListResponse:
        repo = await self.require_admin(actor)
        rows = await repo.units(cursor, limit)
        return StaffCareUnitListResponse(
            items=[
                StaffCareUnitView(care_unit_id=row.id, name=row.name, unit_type=row.unit_type)
                for row in rows[:limit]
            ],
            next_cursor=encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id)
            if len(rows) > limit
            else None,
        )

    async def create(
        self, actor: ActorContext, request: CreateStaffInvitationRequest, trace: str, key: str
    ) -> CreatedStaffInvitationResponse:
        repo = await self.require_admin(actor)
        unit = await repo.unit(request.care_unit_id)
        if unit is None or unit.unit_type not in ROLE_UNITS[request.role_code]:
            raise NotFoundError("Resource not found")
        digest = self.codec.digest_email(request.email)
        await self.identities.acquire_subject_lock(
            subject_digest=digest, key_version=self.codec.key_version
        )
        if await self.identities.list_identities_by_subject(
            subject_digest=digest, key_version=self.codec.key_version
        ):
            raise ConflictError("Account cannot be provisioned")
        token = "wi1_" + secrets.token_urlsafe(32)
        row = StaffInvitation(
            tenant_id=actor.tenant_id,
            issued_by_actor_id=actor.actor_id,
            care_unit_id=unit.id,
            display_name=request.display_name,
            role_code=request.role_code,
            email_digest=digest,
            digest_key_version=self.codec.key_version,
            token_digest=hashlib.sha256(token.encode("ascii")).hexdigest(),
            status="ISSUED",
            expires_at=datetime.now(UTC) + timedelta(hours=24),
            version=1,
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(row, actor.actor_id, "issued", trace, key)
        return CreatedStaffInvitationResponse(
            **invitation_view(row).model_dump(), invitation_token=token
        )

    async def revoke(
        self, actor: ActorContext, invitation_id: UUID, expected_version: int, trace: str, key: str
    ) -> StaffInvitationView:
        repo = await self.require_admin(actor)
        row = await repo.get(invitation_id)
        if row is None:
            raise NotFoundError("Resource not found")
        if row.version != expected_version or row.status != "ISSUED":
            raise ConflictError("Invitation state changed")
        row.status = "REVOKED"
        row.revoked_at = datetime.now(UTC)
        row.version += 1
        await self.session.flush()
        await self._audit(row, actor.actor_id, "revoked", trace, key)
        return invitation_view(row)

    async def accept(self, request: AcceptStaffInvitationRequest, trace: str) -> None:
        require_staff_invitations()
        email_digest = self.codec.digest_email(request.email)
        # Share login/registration's lock so concurrent invitations cannot duplicate identities.
        await self.identities.acquire_subject_lock(
            subject_digest=email_digest, key_version=self.codec.key_version
        )
        token_digest = hashlib.sha256(
            request.invitation_token.get_secret_value().encode("ascii")
        ).hexdigest()
        row = await StaffInvitationRepository.resolve_credential(self.session, token_digest)
        now = datetime.now(UTC)
        if (
            row is None
            or row.status != "ISSUED"
            or row.expires_at <= now
            or row.digest_key_version != self.codec.key_version
            or not hmac.compare_digest(row.email_digest, email_digest)
        ):
            raise AuthenticationError("Authentication required")
        try:
            repo = await self.require_admin(
                ActorContext(row.issued_by_actor_id, "ADMIN", row.tenant_id)
            )
        except NotFoundError:
            raise AuthenticationError("Authentication required") from None
        unit = await repo.unit(row.care_unit_id)
        if unit is None or unit.unit_type not in ROLE_UNITS.get(row.role_code, set()):
            raise AuthenticationError("Authentication required")
        if await self.identities.list_identities_by_subject(
            subject_digest=email_digest, key_version=self.codec.key_version
        ):
            raise AuthenticationError("Authentication required")
        actor = Actor(
            actor_type=row.role_code,
            display_name=row.display_name,
            email=request.email,
            status="ACTIVE",
        )
        self.session.add(actor)
        await self.session.flush()
        self.session.add_all(
            [
                ExternalIdentity(
                    provider="KINSUN",
                    external_subject_digest=email_digest,
                    digest_key_version=self.codec.key_version,
                    actor_id=actor.id,
                    status="ACTIVE",
                    linked_at=now,
                    version=1,
                ),
                PasswordCredential(
                    actor_id=actor.id,
                    password_hash=self.hasher.hash(request.password.get_secret_value()),
                    algorithm="ARGON2ID",
                    parameter_version=self.hasher.policy.parameter_version,
                    status="ACTIVE",
                    failed_attempt_count=0,
                    password_changed_at=now,
                    version=1,
                ),
                *[
                    ActorTenantMembership(
                        actor_id=actor.id,
                        tenant_id=row.tenant_id,
                        care_unit_id=unit_id,
                        role_code=row.role_code,
                        status="ACTIVE",
                        effective_from=now,
                    )
                    for unit_id in (None, row.care_unit_id)
                ],
            ]
        )
        row.status = "ACCEPTED"
        row.accepted_by_actor_id = actor.id
        row.accepted_at = now
        row.version += 1
        await self.session.flush()
        await self._audit(row, actor.id, "accepted", trace, f"staff-invitation:{row.id}:accept")

    async def _audit(
        self, row: StaffInvitation, actor_id: UUID, action: str, trace: str, key: str
    ) -> None:
        await write_outbox_entry(
            self.session,
            event_type=f"staff.invitation.{action}.v1",
            aggregate_type="staff_invitation",
            aggregate_id=row.id,
            aggregate_version=row.version,
            tenant_id=row.tenant_id,
            actor_id=actor_id,
            purpose="ACCOUNT_PROVISIONING",
            payload={
                "invitation_id": str(row.id),
                "care_unit_id": str(row.care_unit_id),
                "role_code": row.role_code,
                "status": row.status,
            },
            trace_id=trace,
            correlation_id=trace,
            idempotency_key=key,
        )
