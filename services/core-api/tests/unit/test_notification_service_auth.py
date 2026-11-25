"""Synthetic worker→Core authentication, with no database/provider calls."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from app.adapters.service_identity import ServiceCredentialSigner, ServiceCredentialVerifier
from app.adapters.service_identity_replay import InMemoryReplayStore
from app.api import notifications
from app.core.auth import ActorContext
from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, ServiceUnavailableError
from app.db.session import get_db_engine
from app.main import app
from app.middleware import notification_service_auth as auth
from app.schemas.notification import DailyLineNotificationJobResponse

SECRET = "synthetic-notification-worker-secret-at-least-32-bytes"
ACTOR = UUID("30000000-0000-4000-8000-000000000010")
TENANT = UUID("30000000-0000-4000-8000-000000000011")
PATH = "/api/v1/internal/notification-jobs/line-daily"
CORRELATION = "30000000-0000-4000-8000-000000000012"
PAYLOAD = {
    "schema_version": "1.0",
    "job_name": "line-daily-family-report",
    "scheduled_for": "2000-01-02T00:00:00+00:00",
    "timezone": "Asia/Taipei",
}
BODY = json.dumps(PAYLOAD, separators=(",", ":")).encode()


@pytest.fixture
def core(monkeypatch):
    verifier = ServiceCredentialVerifier(
        secret=SECRET,
        issuer="kinsun-local",
        expected_subject="notification-worker",
        audience="core-api",
        replay_store=InMemoryReplayStore(),
        max_ttl_seconds=30,
    )
    state = {"resolved": 0, "sent": 0, "role": "SYSTEM_SERVICE", "status": "ACTIVE"}

    async def resolve():
        state["resolved"] += 1
        return ActorContext(
            actor_id=ACTOR, actor_role=state["role"], tenant_id=TENANT, status=state["status"]
        )

    class Service:
        def __init__(self, *args, tenant_id, **kwargs):
            assert tenant_id == TENANT

        async def run(self, request):
            state["sent"] += 1
            return DailyLineNotificationJobResponse(
                status="NO_ELIGIBLE_REPORTS",
                scheduled_for=request.scheduled_for,
                timezone=request.timezone,
                source_period={"start": "2000-01-01", "end": "2000-01-01"},
                counts={"eligible": 0, "sent": 0, "replayed": 0, "skipped": 0, "failed": 0},
                deliveries=[],
            )

    monkeypatch.setattr(auth, "get_notification_service_verifier", lambda: verifier)
    monkeypatch.setattr(auth, "resolve_notification_actor", resolve)
    monkeypatch.setattr(notifications, "DailyLineNotificationService", Service)
    monkeypatch.setattr(notifications, "get_line_messaging_client", lambda: object())
    monkeypatch.setattr(notifications, "get_line_subject_cipher", lambda: object())
    original = app.dependency_overrides.copy()
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        line_daily_notification_enabled=True,
        line_account_link_base_url="https://example.test",
        line_daily_notification_send_time="08:00",
    )
    app.dependency_overrides[get_db_engine] = lambda: SimpleNamespace(is_ready=True)
    try:
        yield state
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


def credential(**kwargs):
    signer_keys = {
        key: kwargs.pop(key)
        for key in list(kwargs)
        if key in {"subject", "audience", "issuer", "secret"}
    }
    signer = ServiceCredentialSigner(
        **{
            "secret": SECRET,
            "issuer": "kinsun-local",
            "subject": "notification-worker",
            "audience": "core-api",
            **signer_keys,
        },
    )
    return signer.sign(
        **{"method": "POST", "path": PATH, "body": BODY, "correlation_id": CORRELATION, **kwargs}
    )


async def send(token=None, *, body=BODY, authorization=None):
    headers = {"Content-Type": "application/json", "X-Correlation-ID": CORRELATION}
    if token:
        headers["X-Kinsun-Service-Credential"] = token
    if authorization:
        headers["Authorization"] = authorization
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://core.test"
    ) as client:
        return await client.post(PATH, content=body, headers=headers)


@pytest.mark.asyncio
async def test_valid_service_identity_dispatches_only_configured_tenant_and_replay_is_denied(core):
    token = credential()
    response = await send(token)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "NO_ELIGIBLE_REPORTS"
    replay = await send(token)
    assert replay.status_code == 401 and core["sent"] == 1 and core["resolved"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"subject": "speech-gateway"},
        {"audience": "agent-runtime"},
        {"issuer": "other"},
        {"secret": "other-synthetic-secret-of-at-least-32-bytes"},
        {"method": "GET"},
        {"path": "/api/v1/other"},
        {"body": b"{}"},
        {"correlation_id": str(ACTOR)},
        {"issued_at": int(time.time()) - 120},
    ],
)
async def test_wrong_direction_binding_signature_or_expiry_cannot_resolve_actor(core, change):
    response = await send(credential(**change))
    assert response.status_code == 401 and core["resolved"] == 0 and core["sent"] == 0
    assert SECRET not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", [None, "Bearer ks1_" + "x" * 43])
async def test_browser_or_anonymous_requests_have_no_service_fallback(core, authorization):
    response = await send(authorization=authorization)
    assert response.status_code == 401 and core["resolved"] == 0 and core["sent"] == 0


@pytest.mark.asyncio
async def test_mixed_browser_and_service_credentials_are_denied(core):
    response = await send(credential(), authorization="Bearer ks1_" + "x" * 43)
    assert response.status_code == 401 and core["sent"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "status"), [("FAMILY_MEMBER", "ACTIVE"), ("SYSTEM_SERVICE", "INACTIVE")]
)
async def test_invalid_live_service_actor_is_denied(core, role, status):
    core.update(role=role, status=status)
    response = await send(credential())
    assert response.status_code == 401 and core["sent"] == 0


@pytest.mark.asyncio
async def test_no_current_membership_is_denied_and_not_replaced_by_caller_scope(core, monkeypatch):
    async def revoked():
        raise AuthenticationError("Authentication required")

    monkeypatch.setattr(auth, "resolve_notification_actor", revoked)
    response = await send(credential())
    assert response.status_code == 401 and core["sent"] == 0


def settings(**values):
    return Settings(
        _env_file=None,
        **{
            "app_env": "development",
            "database_url": "postgresql+asyncpg://test:test@localhost/test",
            "notification_worker_identity_enabled": True,
            "notification_worker_hmac_secret": SECRET,
            "notification_worker_actor_id": ACTOR,
            **values,
        },
    )


@pytest.mark.parametrize(
    "values",
    [
        {"app_env": "production"},
        {"notification_worker_actor_id": None},
        {"notification_worker_hmac_secret": "short"},
        {"speech_service_identity_hmac_secret": SECRET},
    ],
)
def test_partial_reused_or_production_identity_configuration_is_rejected(values):
    with pytest.raises(ValidationError):
        settings(**values)


def test_runtime_verifier_is_durable_and_disabled_profiles_fail_closed(monkeypatch):
    auth.get_notification_service_verifier.cache_clear()
    try:
        monkeypatch.setattr(auth, "get_settings", lambda: settings())
        verifier = auth.get_notification_service_verifier()
        assert verifier._replay_store.durable
        auth.get_notification_service_verifier.cache_clear()
        monkeypatch.setattr(
            auth,
            "get_settings",
            lambda: SimpleNamespace(notification_worker_identity_enabled=False, app_env="test"),
        )
        with pytest.raises(ServiceUnavailableError):
            auth.get_notification_service_verifier()
    finally:
        auth.get_notification_service_verifier.cache_clear()
