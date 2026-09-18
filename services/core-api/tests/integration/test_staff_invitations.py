"""Exercise the real HTTP, identity, membership and onboarding write path."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.adapters.auth.app_session import _extract_bearer_token
from app.bootstrap.dependencies import get_kinsun_identity_codec, get_password_hasher
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.middleware.auth import get_authenticator
from app.models.actor import Actor
from app.models.care_unit import CareUnit
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.staff_invitation import StaffInvitation
from app.models.tenant import Tenant
from app.services.app_session_service import AppSessionPolicy, AppSessionService
from app.services.password_auth_service import PasswordAuthService, PasswordLockoutPolicy


async def exercise_http_workflow(session, email, password, unit_id):
    """Caller owns rollback; no credentials or invite links are printed or persisted to disk."""
    settings = get_settings()
    app = create_app()
    policy = AppSessionPolicy.from_settings(settings)

    async def request_session():
        async with session.begin_nested():
            yield session

    class TransactionAuthenticator:
        async def authenticate(self, request):
            return await AppSessionService(session, policy).authenticate(
                _extract_bearer_token(request)
            )

    app.dependency_overrides[get_db_session] = request_session
    app.dependency_overrides[get_authenticator] = TransactionAuthenticator
    bff = {"X-Kinsun-BFF-Authorization": "Bearer " + settings.kinsun_auth_handoff_secret}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        login = await client.post(
            "/api/v1/internal/auth/kinsun/password/login",
            headers=bff,
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, "Admin login failed"
        headers = {"Authorization": "Bearer " + login.json()["data"]["session_token"]}
        profile = (await client.get("/api/v1/me", headers=headers)).json()["data"]
        assert profile["actor_type"] == "ADMIN"
        units = await client.get("/api/v1/admin/care-units", headers=headers)
        assert units.status_code == 200
        assert str(unit_id) in [x["care_unit_id"] for x in units.json()["data"]["items"]]
        worker_email = f"synthetic-invite-{uuid4().hex}@example.test"
        command = {
            "email": worker_email,
            "display_name": "Synthetic workforce smoke",
            "role_code": "DAYCARE_CARE_WORKER",
            "care_unit_id": str(unit_id),
        }
        issue_headers = {**headers, "Idempotency-Key": str(uuid4())}
        created = await client.post(
            "/api/v1/admin/staff-invitations", headers=issue_headers, json=command
        )
        assert created.status_code == 201, "Issue invitation failed"
        assert created.headers["cache-control"] == "no-store"
        issued = created.json()["data"]
        invitation_id = issued["invitation_id"]
        token = issued["invitation_token"]
        repeated = await client.post(
            "/api/v1/admin/staff-invitations", headers=issue_headers, json=command
        )
        assert repeated.status_code == 409 and token not in repeated.text
        rows = await client.get("/api/v1/admin/staff-invitations", headers=headers)
        assert rows.status_code == 200 and token not in rows.text and worker_email not in rows.text
        acceptance = {
            "email": worker_email,
            "password": "synthetic-workforce-password",
            "invitation_token": token,
        }
        private = "/api/v1/internal/auth/staff-invitations/accept"
        assert (await client.post(private, json=acceptance)).status_code == 401
        wrong = await client.post(
            private, headers=bff, json={**acceptance, "email": "wrong@example.test"}
        )
        assert wrong.status_code == 401
        accepted = await client.post(private, headers=bff, json=acceptance)
        assert accepted.status_code == 200, "Accept invitation failed"
        assert accepted.json()["data"] == {"status": "ACTIVATED"}
        assert (await client.post(private, headers=bff, json=acceptance)).status_code == 401
        worker_login = await client.post(
            "/api/v1/internal/auth/kinsun/password/login",
            headers=bff,
            json={"email": worker_email, "password": acceptance["password"]},
        )
        assert worker_login.status_code == 200, "Worker login failed"
        worker_headers = {"Authorization": "Bearer " + worker_login.json()["data"]["session_token"]}
        worker_profile = (await client.get("/api/v1/me", headers=worker_headers)).json()["data"]
        assert worker_profile["actor_type"] == "DAYCARE_CARE_WORKER"
        assert worker_profile["care_unit_ids"] == [str(unit_id)]
        assert (
            await client.get("/api/v1/admin/staff-invitations", headers=worker_headers)
        ).status_code == 404
        elder = await client.post(
            f"/api/v1/organizations/{profile['tenant_id']}/elders",
            headers={**worker_headers, "Idempotency-Key": str(uuid4())},
            json={"display_name": "Synthetic invitation elder", "care_unit_id": str(unit_id)},
        )
        assert elder.status_code == 201, "New daycare worker cannot onboard elder"
        # The UI must complete both creation and the one-time tablet handoff.
        elder_id = elder.json()["data"]["elder_id"]
        pairing = await client.post(
            f"/api/v1/elders/{elder_id}/assisted-sessions",
            headers=worker_headers,
            json={"client_timezone": "Asia/Taipei"},
        )
        assert pairing.status_code == 201, "Tablet handoff issuance failed"
        exchange_body = {"pairing_token": pairing.json()["data"]["pairing_token"]}
        activated = await client.post(
            "/api/v1/assisted-elder-sessions/exchange", json=exchange_body
        )
        assert activated.status_code == 200, "Tablet activation failed"
        assert (
            await client.post("/api/v1/assisted-elder-sessions/exchange", json=exchange_body)
        ).status_code == 401
        tablet_headers = {"Authorization": "Bearer " + activated.json()["data"]["session_token"]}
        tablet = await client.get("/api/v1/assisted-elder-sessions/current", headers=tablet_headers)
        assert tablet.status_code == 200
        assert tablet.json()["data"]["elder_id"] == elder_id
        # Same-email provisioning may never overwrite the newly established account.
        existing = await client.post(
            "/api/v1/admin/staff-invitations",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json=command,
        )
        assert existing.status_code == 409
        revoked_create = await client.post(
            "/api/v1/admin/staff-invitations",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={**command, "email": f"revoked-{uuid4().hex}@example.test"},
        )
        assert revoked_create.status_code == 201
        revoked = revoked_create.json()["data"]
        revoke_headers = {**headers, "Idempotency-Key": str(uuid4())}
        revoke_url = f"/api/v1/admin/staff-invitations/{revoked['invitation_id']}/revoke"
        for _ in range(2):
            response = await client.post(
                revoke_url, headers=revoke_headers, json={"expected_version": 1}
            )
            assert response.status_code == 200 and response.json()["data"]["status"] == "REVOKED"
        stored = await session.scalar(
            select(StaffInvitation).where(StaffInvitation.id == invitation_id)
        )
        assert stored.status == "ACCEPTED" and stored.version == 2
    return {
        "admin_login": True,
        "issue_accept_replay": True,
        "worker_login": True,
        "care_unit_membership": True,
        "elder_onboarding": True,
        "tablet_handoff_and_activation": True,
        "revoke_replay": True,
    }


@pytest.mark.asyncio
async def test_staff_invitation_http_workflow(db_session, monkeypatch):
    # The workflow must also work in CI without a developer .env filling missing secrets.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key, value in {
        "STAFF_INVITATIONS_ENABLED": "true",
        "KINSUN_NATIVE_AUTH_ENABLED": "true",
        "APP_ENV": "development",
        "APP_SESSION_AUTH_ENABLED": "true",
        "ASSISTED_ELDER_SESSIONS_ENABLED": "true",
        "KINSUN_IDENTITY_HMAC_SECRET": "synthetic-workforce-identity-secret-32-bytes",
        "KINSUN_EMAIL_CHALLENGE_HMAC_SECRET": "synthetic-workforce-challenge-secret-32-bytes",
        "KINSUN_AUTH_HANDOFF_SECRET": "synthetic-workforce-handoff-secret-32-bytes",
        "FAMILY_INVITATION_HMAC_SECRET": "synthetic-workforce-family-secret-32-bytes",
        "KINSUN_EMAIL_DELIVERY_MODE": "synthetic",
        "KINSUN_SYNTHETIC_EMAIL_CODE_SECRET": "246810",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        tenant_id, actor_id, unit_id = uuid4(), uuid4(), uuid4()
        email = f"synthetic-admin-{uuid4().hex}@example.test"
        password = "synthetic-admin-password"
        db_session.add_all(
            [
                Tenant(id=tenant_id, name="Synthetic invite tenant", tenant_type="DEMO"),
                Actor(
                    id=actor_id,
                    actor_type="ADMIN",
                    display_name="Synthetic admin",
                    email=email,
                    status="ACTIVE",
                ),
            ]
        )
        await db_session.flush()
        db_session.add_all(
            [
                CareUnit(
                    id=unit_id,
                    tenant_id=tenant_id,
                    name="Synthetic daycare",
                    unit_type="DAYCARE_CENTER",
                ),
                ActorTenantMembership(
                    actor_id=actor_id,
                    tenant_id=tenant_id,
                    care_unit_id=None,
                    role_code="ADMIN",
                    status="ACTIVE",
                    effective_from=datetime.now(UTC),
                ),
                ExternalIdentity(
                    provider="KINSUN",
                    external_subject_digest=get_kinsun_identity_codec().digest_email(email),
                    digest_key_version=1,
                    actor_id=actor_id,
                    status="ACTIVE",
                    linked_at=datetime.now(UTC),
                    version=1,
                ),
            ]
        )
        await PasswordAuthService(
            db_session,
            identity_codec=get_kinsun_identity_codec(),
            password_hasher=get_password_hasher(),
            app_session_service=AppSessionService(
                db_session, AppSessionPolicy.from_settings(settings)
            ),
            lockout_policy=PasswordLockoutPolicy(max_attempts=5, duration=timedelta(minutes=15)),
        ).create_credential(actor_id=actor_id, password=password)
        await db_session.flush()
        await exercise_http_workflow(db_session, email, password, unit_id)
    finally:
        get_settings.cache_clear()
