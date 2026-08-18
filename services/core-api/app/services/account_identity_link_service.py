"""Explicit LINE linking and bounded empty-account consolidation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.oidc import LineTokenVerifier
from app.events.outbox_writer import write_outbox_entry
from app.models.account_merge import AccountMergeRequest
from app.models.line_identity import ExternalIdentity
from app.repositories.account_identity_repo import AccountIdentityRepository
from app.repositories.app_session_repo import ResolvedAppSession
from app.services.account_merge_tokens import AccountMergeTokenCodec
from app.services.app_session_service import AppSessionService, IssuedAppSession
from app.services.app_session_tokens import AppSessionTokenCodec
from app.services.line_identity_codec import LineIdentityCodec

_AUTHENTICATION_REQUIRED = "Authentication required"


@dataclass(frozen=True)
class IdentityMethodStatus:
    google_linked: bool
    line_linked: bool
    recently_authenticated: bool


@dataclass(frozen=True)
class LinkedIdentity:
    status: Literal["LINKED", "ALREADY_LINKED"]


@dataclass(frozen=True)
class MergeRequired:
    status: Literal["MERGE_REQUIRED"]
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class ManualReviewRequired:
    status: Literal["MANUAL_REVIEW_REQUIRED"]


@dataclass(frozen=True)
class MergeCompleted:
    status: Literal["MERGED"]
    session: IssuedAppSession


LinkResult = LinkedIdentity | MergeRequired | ManualReviewRequired
MergeResult = MergeCompleted | ManualReviewRequired


class AccountIdentityLinkService:
    """Require a recent App Session plus fresh LINE proof before any link."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        verifier: LineTokenVerifier,
        identity_codec: LineIdentityCodec,
        app_session_service: AppSessionService,
        merge_ttl: timedelta,
        repository: AccountIdentityRepository | None = None,
        merge_token_codec: AccountMergeTokenCodec | None = None,
        app_session_token_codec: AppSessionTokenCodec | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not timedelta(seconds=60) <= merge_ttl <= timedelta(minutes=15):
            raise ValueError("Account merge TTL must be between 60 and 900 seconds")
        self._session = session
        self._verifier = verifier
        self._identity_codec = identity_codec
        self._app_sessions = app_session_service
        self._merge_ttl = merge_ttl
        self._repository = repository or AccountIdentityRepository(session)
        self._merge_tokens = merge_token_codec or AccountMergeTokenCodec()
        self._session_tokens = app_session_token_codec or AppSessionTokenCodec()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def link_line(
        self,
        *,
        actor_context: ActorContext,
        app_session_token: str,
        id_token: str,
        expected_nonce: str,
        trace_id: str,
    ) -> LinkResult:
        target_session = await self._resolve_current_session(
            actor_context=actor_context,
            app_session_token=app_session_token,
            for_update=True,
            require_recent=True,
        )
        target_identities = await self._repository.list_active_identities(
            actor_id=actor_context.actor_id,
            for_update=True,
        )
        if not any(identity.provider == "GOOGLE" for identity in target_identities):
            raise ConflictError("A verified Google identity is required before linking LINE")

        verified = await self._verifier.verify_id_token(
            id_token,
            expected_nonce=expected_nonce,
        )
        subject_digest = self._identity_codec.digest_subject(verified.subject)
        key_version = self._identity_codec.key_version
        await self._repository.acquire_subject_lock(
            subject_digest=subject_digest,
            key_version=key_version,
        )
        identities = await self._repository.list_identities_by_subject(
            subject_digest=subject_digest,
            key_version=key_version,
            for_update=True,
        )
        active = [identity for identity in identities if identity.status == "ACTIVE"]
        if len(active) > 1 or (identities and not active):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        existing_target_line = next(
            (identity for identity in target_identities if identity.provider == "LINE"),
            None,
        )
        now = self._clock()
        if active and active[0].actor_id == actor_context.actor_id:
            if existing_target_line is None or existing_target_line.id != active[0].id:
                raise AuthenticationError(_AUTHENTICATION_REQUIRED)
            active[0].last_seen_at = now
            active[0].version += 1
            await self._repository.flush()
            return LinkedIdentity(status="ALREADY_LINKED")
        if existing_target_line is not None:
            raise ConflictError("This account already has a different LINE identity")

        if not active:
            identity = ExternalIdentity(
                provider="LINE",
                external_subject_digest=subject_digest,
                digest_key_version=key_version,
                actor_id=actor_context.actor_id,
                status="ACTIVE",
                linked_at=now,
                last_seen_at=now,
                version=1,
            )
            self._repository.add_identity(identity)
            await self._repository.flush()
            await self._write_link_event(
                identity=identity,
                actor_context=actor_context,
                trace_id=trace_id,
                event_suffix="direct-link",
            )
            return LinkedIdentity(status="LINKED")

        source_identity = active[0]
        actors = await self._repository.lock_actors(
            source_identity.actor_id,
            actor_context.actor_id,
        )
        target_actor = actors.get(actor_context.actor_id)
        source_actor = actors.get(source_identity.actor_id)
        safe_skeleton = None
        if (
            target_actor is not None
            and source_actor is not None
            and target_actor.status == "ACTIVE"
            and source_actor.status == "ACTIVE"
            and target_actor.actor_type == source_actor.actor_type == "ELDER"
        ):
            safe_skeleton = await self._repository.empty_elder_skeleton(
                source_actor_id=source_identity.actor_id,
                source_identity_id=source_identity.id,
            )

        open_merge = await self._repository.get_open_merge(
            source_actor_id=source_identity.actor_id,
            target_actor_id=actor_context.actor_id,
            for_update=True,
        )
        if open_merge is not None:
            if open_merge.status == "PENDING_REVIEW" and safe_skeleton is None:
                return ManualReviewRequired(status="MANUAL_REVIEW_REQUIRED")
            open_merge.status = "EXPIRED" if open_merge.expires_at <= now else "REVOKED"
            open_merge.version += 1
            await self._repository.flush()

        issued = self._merge_tokens.issue()
        merge_status: Literal["PENDING_CONFIRMATION", "PENDING_REVIEW"] = (
            "PENDING_CONFIRMATION" if safe_skeleton is not None else "PENDING_REVIEW"
        )
        merge = AccountMergeRequest(
            token_digest=issued.digest,
            source_actor_id=source_identity.actor_id,
            target_actor_id=actor_context.actor_id,
            source_external_identity_id=source_identity.id,
            target_external_identity_id=target_session.identity.id,
            target_app_session_id=target_session.app_session.id,
            status=merge_status,
            reason_code=None if safe_skeleton is not None else "SOURCE_HAS_DOMAIN_DATA",
            expires_at=now + self._merge_ttl,
            completed_at=None,
            version=1,
        )
        self._repository.add_merge(merge)
        await self._repository.flush()
        if safe_skeleton is None:
            return ManualReviewRequired(status="MANUAL_REVIEW_REQUIRED")
        return MergeRequired(
            status="MERGE_REQUIRED",
            token=issued.value,
            expires_at=merge.expires_at,
        )

    async def confirm_merge(
        self,
        *,
        actor_context: ActorContext,
        app_session_token: str,
        merge_token: str,
        trace_id: str,
    ) -> MergeResult:
        try:
            merge_digest = self._merge_tokens.digest(merge_token)
        except ValueError:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        merge = await self._repository.get_merge_by_token_digest(
            merge_digest,
            for_update=True,
        )
        now = self._clock()
        if (
            merge is None
            or merge.status != "PENDING_CONFIRMATION"
            or merge.expires_at <= now
            or merge.target_actor_id != actor_context.actor_id
        ):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        target_session = await self._resolve_current_session(
            actor_context=actor_context,
            app_session_token=app_session_token,
            for_update=True,
            require_recent=True,
        )
        if (
            target_session.app_session.id != merge.target_app_session_id
            or target_session.identity.id != merge.target_external_identity_id
        ):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        actors = await self._repository.lock_actors(
            merge.source_actor_id,
            merge.target_actor_id,
        )
        source_actor = actors.get(merge.source_actor_id)
        target_actor = actors.get(merge.target_actor_id)
        source_identity = await self._repository.get_identity(
            merge.source_external_identity_id,
            for_update=True,
        )
        target_identities = await self._repository.list_active_identities(
            actor_id=merge.target_actor_id,
            for_update=True,
        )
        if (
            source_actor is None
            or target_actor is None
            or source_actor.status != "ACTIVE"
            or target_actor.status != "ACTIVE"
            or source_actor.actor_type != target_actor.actor_type
            or source_identity is None
            or source_identity.status != "ACTIVE"
            or source_identity.provider != "LINE"
            or source_identity.actor_id != source_actor.id
            or any(identity.provider == "LINE" for identity in target_identities)
        ):
            raise ConflictError("Account merge state changed")

        skeleton = await self._repository.empty_elder_skeleton(
            source_actor_id=source_actor.id,
            source_identity_id=source_identity.id,
        )
        if skeleton is None:
            merge.status = "PENDING_REVIEW"
            merge.reason_code = "SOURCE_HAS_DOMAIN_DATA"
            merge.version += 1
            await self._repository.flush()
            return ManualReviewRequired(status="MANUAL_REVIEW_REQUIRED")

        await self._repository.revoke_active_sessions(
            actor_ids={source_actor.id, target_actor.id},
            now=now,
        )
        source_identity.status = "REVOKED"
        source_identity.revoked_at = now
        source_identity.version += 1
        skeleton.actor.status = "INACTIVE"
        skeleton.membership.status = "INACTIVE"
        skeleton.membership.effective_to = now
        skeleton.elder.status = "INACTIVE"
        skeleton.tenant.status = "INACTIVE"
        await self._repository.flush()

        target_line = ExternalIdentity(
            provider="LINE",
            external_subject_digest=source_identity.external_subject_digest,
            digest_key_version=source_identity.digest_key_version,
            actor_id=target_actor.id,
            status="ACTIVE",
            linked_at=now,
            last_seen_at=now,
            version=1,
        )
        self._repository.add_identity(target_line)
        merge.status = "COMPLETED"
        merge.reason_code = None
        merge.completed_at = now
        merge.version += 1
        await self._repository.flush()

        await self._write_merge_events(
            merge=merge,
            source_identity=source_identity,
            target_identity=target_line,
            actor_context=actor_context,
            trace_id=trace_id,
        )
        issued_session = await self._app_sessions.issue(external_identity_id=target_line.id)
        return MergeCompleted(status="MERGED", session=issued_session)

    async def _resolve_current_session(
        self,
        *,
        actor_context: ActorContext,
        app_session_token: str,
        for_update: bool,
        require_recent: bool,
    ) -> ResolvedAppSession:
        try:
            token_digest = self._session_tokens.digest(app_session_token)
        except ValueError:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        resolved = await self._repository.get_app_session(
            token_digest,
            for_update=for_update,
        )
        now = self._clock()
        if (
            resolved is None
            or resolved.actor.id != actor_context.actor_id
            or resolved.actor.status != "ACTIVE"
            or resolved.identity.status != "ACTIVE"
            or resolved.app_session.status != "ACTIVE"
            or resolved.app_session.authenticated_at > now
            or resolved.app_session.idle_expires_at <= now
            or resolved.app_session.absolute_expires_at <= now
            or (
                require_recent
                and not self._app_sessions.is_recently_authenticated(resolved.app_session)
            )
        ):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        return resolved

    async def _write_link_event(
        self,
        *,
        identity: ExternalIdentity,
        actor_context: ActorContext,
        trace_id: str,
        event_suffix: str,
    ) -> None:
        await write_outbox_entry(
            self._session,
            event_type="external_identity.linked.v1",
            aggregate_type="external_identity",
            aggregate_id=identity.id,
            aggregate_version=identity.version,
            tenant_id=actor_context.tenant_id,
            actor_id=actor_context.actor_id,
            purpose="AUTHENTICATION",
            payload={
                "external_identity_id": str(identity.id),
                "actor_id": str(actor_context.actor_id),
                "provider": "LINE",
                "status": "ACTIVE",
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=f"{trace_id}:{event_suffix}",
        )

    async def _write_merge_events(
        self,
        *,
        merge: AccountMergeRequest,
        source_identity: ExternalIdentity,
        target_identity: ExternalIdentity,
        actor_context: ActorContext,
        trace_id: str,
    ) -> None:
        await write_outbox_entry(
            self._session,
            event_type="actor.account-consolidated.v1",
            aggregate_type="account_merge_request",
            aggregate_id=merge.id,
            aggregate_version=merge.version,
            tenant_id=actor_context.tenant_id,
            actor_id=actor_context.actor_id,
            purpose="AUTHENTICATION",
            payload={
                "account_merge_request_id": str(merge.id),
                "source_actor_id": str(merge.source_actor_id),
                "target_actor_id": str(merge.target_actor_id),
                "source_external_identity_id": str(source_identity.id),
                "target_external_identity_id": str(target_identity.id),
                "provider": "LINE",
                "status": "COMPLETED",
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=f"{trace_id}:account-consolidation",
        )
        await self._write_link_event(
            identity=target_identity,
            actor_context=actor_context,
            trace_id=trace_id,
            event_suffix="merge-link",
        )


class AccountIdentityStatusService:
    """Read linked methods only after resolving the exact App Session."""

    def __init__(
        self,
        *,
        repository: AccountIdentityRepository,
        app_session_service: AppSessionService,
        app_session_token_codec: AppSessionTokenCodec | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._app_sessions = app_session_service
        self._session_tokens = app_session_token_codec or AppSessionTokenCodec()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def status(
        self,
        *,
        actor_context: ActorContext,
        app_session_token: str,
    ) -> IdentityMethodStatus:
        try:
            token_digest = self._session_tokens.digest(app_session_token)
        except ValueError:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        resolved = await self._repository.get_app_session(token_digest, for_update=False)
        now = self._clock()
        if (
            resolved is None
            or resolved.actor.id != actor_context.actor_id
            or resolved.actor.status != "ACTIVE"
            or resolved.identity.status != "ACTIVE"
            or resolved.app_session.status != "ACTIVE"
            or resolved.app_session.idle_expires_at <= now
            or resolved.app_session.absolute_expires_at <= now
        ):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        identities = await self._repository.list_active_identities(actor_id=actor_context.actor_id)
        return IdentityMethodStatus(
            google_linked=any(identity.provider == "GOOGLE" for identity in identities),
            line_linked=any(identity.provider == "LINE" for identity in identities),
            recently_authenticated=self._app_sessions.is_recently_authenticated(
                resolved.app_session
            ),
        )
