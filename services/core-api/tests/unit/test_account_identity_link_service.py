"""Explicit account-link and empty-account consolidation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.adapters.auth.line_oidc import VerifiedLineIdentity
from app.middleware.auth import ActorContext
from app.models.actor import Actor
from app.models.app_session import AppSession
from app.models.elder import Elder
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant
from app.repositories.account_identity_repo import EmptyElderAccountSkeleton
from app.repositories.app_session_repo import ResolvedAppSession
from app.services.account_identity_link_service import (
    AccountIdentityLinkService,
    LinkedIdentity,
    ManualReviewRequired,
    MergeCompleted,
    MergeRequired,
)
from app.services.app_session_service import IssuedAppSession
from app.services.line_identity_codec import LineIdentityCodec

_NOW = datetime(2026, 8, 12, 4, 0, tzinfo=UTC)
_APP_TOKEN = "ks1_" + "a" * 43


class _Verifier:
    async def verify_id_token(self, token: str, *, expected_nonce: str):
        assert token == "header.payload.signature"
        assert expected_nonce == "n" * 32
        return VerifiedLineIdentity(subject="U1234567890abcdef")


class _AppSessions:
    def __init__(self) -> None:
        self.issued_for = []
        self.issued = IssuedAppSession(
            token="ks1_" + "z" * 43,
            session_id=uuid4(),
            idle_expires_at=_NOW + timedelta(days=7),
            absolute_expires_at=_NOW + timedelta(days=30),
        )

    def is_recently_authenticated(self, _app_session: AppSession) -> bool:
        return True

    async def issue(self, *, external_identity_id):
        self.issued_for.append(external_identity_id)
        return self.issued


def _actor(actor_type: str = "ELDER") -> Actor:
    value = Actor(
        actor_type=actor_type,
        cognito_sub=None,
        display_name="Synthetic",
        status="ACTIVE",
    )
    value.id = uuid4()
    return value


def _identity(actor: Actor, provider: str, digest: str) -> ExternalIdentity:
    value = ExternalIdentity(
        provider=provider,
        external_subject_digest=digest,
        digest_key_version=1,
        actor_id=actor.id,
        status="ACTIVE",
        version=1,
    )
    value.id = uuid4()
    return value


def _session(actor: Actor, identity: ExternalIdentity) -> AppSession:
    value = AppSession(
        token_digest="b" * 64,
        actor_id=actor.id,
        external_identity_id=identity.id,
        status="ACTIVE",
        authenticated_at=_NOW - timedelta(minutes=1),
        last_seen_at=_NOW - timedelta(seconds=30),
        idle_expires_at=_NOW + timedelta(days=7),
        absolute_expires_at=_NOW + timedelta(days=30),
        revoked_at=None,
        version=1,
    )
    value.id = uuid4()
    return value


def _skeleton(actor: Actor, identity: ExternalIdentity) -> EmptyElderAccountSkeleton:
    tenant = Tenant(
        tenant_type="HOUSEHOLD",
        name="Synthetic household",
        status="ACTIVE",
        timezone="Asia/Taipei",
    )
    tenant.id = uuid4()
    elder = Elder(
        tenant_id=tenant.id,
        actor_id=actor.id,
        display_name="Synthetic",
        primary_care_setting="INDEPENDENT",
        status="ACTIVE",
        preferred_language="ZH_TW",
        response_length_preference="SHORT",
        timezone="Asia/Taipei",
    )
    elder.id = uuid4()
    membership = ActorTenantMembership(
        actor_id=actor.id,
        tenant_id=tenant.id,
        care_unit_id=None,
        role_code="ELDER",
        status="ACTIVE",
        effective_from=_NOW - timedelta(minutes=5),
        effective_to=None,
    )
    membership.id = uuid4()
    return EmptyElderAccountSkeleton(
        actor=actor,
        identity=identity,
        tenant=tenant,
        membership=membership,
        elder=elder,
    )


class _Repository:
    def __init__(self, *, source_has_skeleton: bool = True) -> None:
        self.target_actor = _actor()
        self.target_google = _identity(self.target_actor, "GOOGLE", "g" * 64)
        self.target_session = _session(self.target_actor, self.target_google)
        self.source_actor = _actor()
        self.source_line = _identity(self.source_actor, "LINE", "l" * 64)
        self.source_has_skeleton = source_has_skeleton
        self.source_skeleton = _skeleton(self.source_actor, self.source_line)
        self.subject_identities: list[ExternalIdentity] = []
        self.target_identities = [self.target_google]
        self.added_identities: list[ExternalIdentity] = []
        self.added_merges = []
        self.revoked_actor_ids = None

    async def get_app_session(self, _digest, *, for_update=False):
        return ResolvedAppSession(
            app_session=self.target_session,
            identity=self.target_google,
            actor=self.target_actor,
        )

    async def list_active_identities(self, *, actor_id, for_update=False):
        return self.target_identities if actor_id == self.target_actor.id else [self.source_line]

    async def acquire_subject_lock(self, **_kwargs):
        return None

    async def list_identities_by_subject(self, **_kwargs):
        return self.subject_identities

    async def lock_actors(self, *actor_ids):
        del actor_ids
        return {
            self.target_actor.id: self.target_actor,
            self.source_actor.id: self.source_actor,
        }

    async def empty_elder_skeleton(self, **_kwargs):
        return self.source_skeleton if self.source_has_skeleton else None

    async def get_open_merge(self, **_kwargs):
        return None

    def add_identity(self, identity):
        identity.id = uuid4()
        self.added_identities.append(identity)
        if identity.actor_id == self.target_actor.id:
            self.target_identities.append(identity)

    def add_merge(self, merge):
        merge.id = uuid4()
        self.added_merges.append(merge)

    async def get_merge_by_token_digest(self, token_digest, *, for_update=False):
        return next(
            (merge for merge in self.added_merges if merge.token_digest == token_digest),
            None,
        )

    async def get_identity(self, identity_id, *, for_update=False):
        return self.source_line if identity_id == self.source_line.id else None

    async def revoke_active_sessions(self, *, actor_ids, now):
        del now
        self.revoked_actor_ids = actor_ids
        self.target_session.status = "REVOKED"
        self.target_session.revoked_at = _NOW

    async def flush(self):
        return None


def _service(repository: _Repository, app_sessions: _AppSessions) -> AccountIdentityLinkService:
    return AccountIdentityLinkService(
        object(),  # type: ignore[arg-type]
        verifier=_Verifier(),  # type: ignore[arg-type]
        identity_codec=LineIdentityCodec("line-identity-secret-material-at-least-32-bytes", 1),
        app_session_service=app_sessions,  # type: ignore[arg-type]
        merge_ttl=timedelta(minutes=10),
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )


def _context(repository: _Repository) -> ActorContext:
    return ActorContext(
        actor_id=repository.target_actor.id,
        actor_role="ELDER",
        tenant_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_unbound_line_identity_links_to_recent_google_actor(monkeypatch) -> None:
    repository = _Repository()
    app_sessions = _AppSessions()
    monkeypatch.setattr(
        "app.services.account_identity_link_service.write_outbox_entry",
        AsyncMock(),
    )

    result = await _service(repository, app_sessions).link_line(
        actor_context=_context(repository),
        app_session_token=_APP_TOKEN,
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        trace_id="trace-link",
    )

    assert isinstance(result, LinkedIdentity)
    assert result.status == "LINKED"
    assert repository.added_identities[0].actor_id == repository.target_actor.id


@pytest.mark.asyncio
async def test_existing_empty_line_actor_requires_single_use_confirmation(monkeypatch) -> None:
    repository = _Repository(source_has_skeleton=True)
    repository.subject_identities = [repository.source_line]
    monkeypatch.setattr(
        "app.services.account_identity_link_service.write_outbox_entry",
        AsyncMock(),
    )

    result = await _service(repository, _AppSessions()).link_line(
        actor_context=_context(repository),
        app_session_token=_APP_TOKEN,
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        trace_id="trace-merge",
    )

    assert isinstance(result, MergeRequired)
    assert repository.added_merges[0].status == "PENDING_CONFIRMATION"
    assert result.token not in vars(repository.added_merges[0]).values()


@pytest.mark.asyncio
async def test_existing_line_actor_with_domain_data_requires_manual_review(monkeypatch) -> None:
    repository = _Repository(source_has_skeleton=False)
    repository.subject_identities = [repository.source_line]
    monkeypatch.setattr(
        "app.services.account_identity_link_service.write_outbox_entry",
        AsyncMock(),
    )

    result = await _service(repository, _AppSessions()).link_line(
        actor_context=_context(repository),
        app_session_token=_APP_TOKEN,
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        trace_id="trace-review",
    )

    assert isinstance(result, ManualReviewRequired)
    assert repository.added_merges[0].status == "PENDING_REVIEW"


@pytest.mark.asyncio
async def test_confirm_empty_account_merge_revokes_old_sessions_and_issues_new_one(
    monkeypatch,
) -> None:
    repository = _Repository(source_has_skeleton=True)
    repository.subject_identities = [repository.source_line]
    app_sessions = _AppSessions()
    monkeypatch.setattr(
        "app.services.account_identity_link_service.write_outbox_entry",
        AsyncMock(),
    )
    service = _service(repository, app_sessions)
    pending = await service.link_line(
        actor_context=_context(repository),
        app_session_token=_APP_TOKEN,
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        trace_id="trace-merge-start",
    )
    assert isinstance(pending, MergeRequired)

    result = await service.confirm_merge(
        actor_context=_context(repository),
        app_session_token=_APP_TOKEN,
        merge_token=pending.token,
        trace_id="trace-merge-confirm",
    )

    assert isinstance(result, MergeCompleted)
    assert repository.revoked_actor_ids == {
        repository.source_actor.id,
        repository.target_actor.id,
    }
    assert repository.source_line.status == "REVOKED"
    assert repository.source_actor.status == "INACTIVE"
    assert repository.source_skeleton.elder.status == "INACTIVE"
    assert repository.source_skeleton.tenant.status == "INACTIVE"
    assert repository.added_merges[0].status == "COMPLETED"
    assert app_sessions.issued_for == [repository.added_identities[-1].id]
