"""Workforce invitation authorization, privacy and single-use activation."""

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.auth import ActorContext
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.models.actor import Actor
from app.models.membership import ActorTenantMembership
from app.models.password_credential import PasswordCredential
from app.models.staff_invitation import StaffInvitation
from app.schemas.staff_invitation import AcceptStaffInvitationRequest, CreateStaffInvitationRequest
from app.services import staff_invitation_service as module
from app.services.kinsun_identity_codec import KinsunIdentityCodec

TOKEN = "wi1_" + "a" * 43
EMAIL = "new.worker@example.test"
CODEC = KinsunIdentityCodec("synthetic-workforce-identity-secret-32-bytes", 1)


@pytest.fixture
def setup(monkeypatch):
    session = MagicMock()
    session.flush = AsyncMock()
    session.scalar = AsyncMock()
    hasher = SimpleNamespace(
        hash=lambda _: "argon2-hash", policy=SimpleNamespace(parameter_version=1)
    )
    service = module.StaffInvitationService(session, CODEC, hasher)
    service.identities = SimpleNamespace(
        acquire_subject_lock=AsyncMock(), list_identities_by_subject=AsyncMock(return_value=[])
    )
    context = ActorContext(uuid4(), "ADMIN", uuid4())
    unit = SimpleNamespace(id=uuid4(), unit_type="DAYCARE_CENTER")
    repo = SimpleNamespace(unit=AsyncMock(return_value=unit), get=AsyncMock())
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            staff_invitations_enabled=True, app_env="development", kinsun_native_auth_enabled=True
        ),
    )
    monkeypatch.setattr(module, "write_outbox_entry", AsyncMock())
    return service, session, context, unit, repo


def invitation(context, unit, **kwargs):
    return StaffInvitation(
        id=uuid4(),
        tenant_id=context.tenant_id,
        issued_by_actor_id=context.actor_id,
        care_unit_id=unit.id,
        display_name="Synthetic worker",
        role_code="DAYCARE_CARE_WORKER",
        email_digest=CODEC.digest_email(EMAIL),
        digest_key_version=1,
        token_digest=hashlib.sha256(TOKEN.encode()).hexdigest(),
        version=1,
        status=kwargs.get("status", "ISSUED"),
        expires_at=kwargs.get("expires_at", datetime.now(UTC) + timedelta(hours=1)),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role", ["DAYCARE_CARE_WORKER", "HOME_CARE_WORKER", "FAMILY_MEMBER", "ELDER"]
)
async def test_non_admin_cannot_issue_or_list(setup, role):
    service, session, context, _, _ = setup
    with pytest.raises(NotFoundError):
        await service.require_admin(ActorContext(context.actor_id, role, context.tenant_id))
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_rechecks_live_membership_and_tenant(setup, monkeypatch):
    service, session, context, _, _ = setup
    session.scalar.return_value = Actor(id=context.actor_id, actor_type="ADMIN", status="ACTIVE")
    resolver = AsyncMock(return_value=ActorContext(context.actor_id, "ADMIN", uuid4()))
    monkeypatch.setattr(module, "resolve_active_actor_context", resolver)
    with pytest.raises(NotFoundError):
        await service.require_admin(context)
    resolver.return_value = context
    assert (await service.require_admin(context)).tenant_id == context.tenant_id
    resolver.side_effect = AuthenticationError("Authentication required")
    with pytest.raises(NotFoundError):
        await service.require_admin(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("unit_type", [None, "HOME_CARE_AGENCY"])
async def test_create_rejects_foreign_inactive_or_wrong_type_unit(setup, unit_type):
    service, session, context, unit, repo = setup
    service.require_admin = AsyncMock(return_value=repo)
    repo.unit.return_value = None if unit_type is None else SimpleNamespace(unit_type=unit_type)
    request = CreateStaffInvitationRequest(
        email=EMAIL,
        display_name="Demo worker",
        role_code="DAYCARE_CARE_WORKER",
        care_unit_id=unit.id,
    )
    with pytest.raises(NotFoundError):
        await service.create(context, request, "trace", "key")
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_issue_keeps_only_hash_and_list_never_leaks_token(setup):
    service, session, context, unit, repo = setup
    service.require_admin = AsyncMock(return_value=repo)

    async def flush():
        row = session.add.call_args.args[0]
        row.id = row.id or uuid4()

    session.flush.side_effect = flush
    result = await service.create(
        context,
        CreateStaffInvitationRequest(
            email=EMAIL,
            display_name="Demo worker",
            role_code="DAYCARE_CARE_WORKER",
            care_unit_id=unit.id,
        ),
        "trace",
        "key",
    )
    row = session.add.call_args.args[0]
    assert row.token_digest == hashlib.sha256(result.invitation_token.encode()).hexdigest()
    assert EMAIL not in repr(row.__dict__) and result.invitation_token not in repr(row.__dict__)
    assert "invitation_token" not in module.invitation_view(row).model_dump()
    event = module.write_outbox_entry.call_args.kwargs
    assert set(event["payload"]) == {"invitation_id", "care_unit_id", "role_code", "status"}


@pytest.mark.asyncio
async def test_accept_creates_role_and_both_memberships_then_replay_fails(setup):
    service, session, context, unit, repo = setup
    row = invitation(context, unit)
    session.scalar.return_value = row
    service.require_admin = AsyncMock(return_value=repo)

    async def flush():
        for call in session.add.call_args_list:
            if isinstance(call.args[0], Actor):
                call.args[0].id = call.args[0].id or uuid4()

    session.flush.side_effect = flush
    request = AcceptStaffInvitationRequest(
        email=EMAIL, password="synthetic-demo-password", invitation_token=TOKEN
    )
    await service.accept(request, "trace")
    actor = session.add.call_args.args[0]
    added = session.add_all.call_args.args[0]
    memberships = [x for x in added if isinstance(x, ActorTenantMembership)]
    assert actor.actor_type == "DAYCARE_CARE_WORKER"
    assert {x.care_unit_id for x in memberships} == {None, unit.id}
    assert all(
        x.tenant_id == context.tenant_id and x.role_code == actor.actor_type for x in memberships
    )
    assert (
        next(x for x in added if isinstance(x, PasswordCredential)).password_hash == "argon2-hash"
    )
    assert row.status == "ACCEPTED" and row.accepted_by_actor_id == actor.id and row.version == 2
    with pytest.raises(AuthenticationError):
        await service.accept(request, "replay")
    assert session.add.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["missing", "expired", "revoked", "email", "key", "issuer", "unit", "existing"]
)
async def test_invalid_activation_creates_nothing(setup, failure):
    service, session, context, unit, repo = setup
    row = invitation(context, unit)
    session.scalar.return_value = row
    service.require_admin = AsyncMock(return_value=repo)
    if failure == "missing":
        session.scalar.return_value = None
    elif failure == "expired":
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif failure == "revoked":
        row.status = "REVOKED"
    elif failure == "email":
        row.email_digest = CODEC.digest_email("different@example.test")
    elif failure == "key":
        row.digest_key_version = 2
    elif failure == "issuer":
        service.require_admin.side_effect = NotFoundError("Resource not found")
    elif failure == "unit":
        repo.unit.return_value = None
    elif failure == "existing":
        service.identities.list_identities_by_subject.return_value = [object()]
    with pytest.raises(AuthenticationError):
        await service.accept(
            AcceptStaffInvitationRequest(
                email=EMAIL, password="synthetic-demo-password", invitation_token=TOKEN
            ),
            "trace",
        )
    session.add.assert_not_called()
    session.add_all.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_is_versioned_and_tenant_scoped(setup):
    service, _, context, unit, repo = setup
    service.require_admin = AsyncMock(return_value=repo)
    row = invitation(context, unit)
    repo.get.return_value = row
    with pytest.raises(ConflictError):
        await service.revoke(context, row.id, 2, "trace", "key")
    assert row.status == "ISSUED"
    result = await service.revoke(context, row.id, 1, "trace", "key")
    assert result.status == "REVOKED" and row.version == 2
    repo.get.return_value = None
    with pytest.raises(NotFoundError):
        await service.revoke(context, uuid4(), 1, "trace", "key")


@pytest.mark.parametrize("field,value", [("role_code", "ADMIN"), ("tenant_id", str(uuid4()))])
def test_client_cannot_assign_admin_or_override_tenant(field, value):
    data = dict(
        email=EMAIL, display_name="Demo", role_code="DAYCARE_CARE_WORKER", care_unit_id=uuid4()
    )
    data[field] = value
    with pytest.raises(ValidationError):
        CreateStaffInvitationRequest.model_validate(data)


@pytest.mark.parametrize("password", ["short", "a" * 129, "a" * 12 + "\x00"])
def test_password_policy(password):
    with pytest.raises(ValidationError):
        AcceptStaffInvitationRequest(email=EMAIL, password=password, invitation_token=TOKEN)


@pytest.mark.parametrize(
    "flag,environment,native",
    [(False, "development", True), (True, "production", True), (True, "development", False)],
)
def test_gate_fails_closed(monkeypatch, flag, environment, native):
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            staff_invitations_enabled=flag, app_env=environment, kinsun_native_auth_enabled=native
        ),
    )
    with pytest.raises(NotFoundError):
        module.require_staff_invitations()
