from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api import kinsun_email_auth as api_module
from app.api.error_handlers import register_exception_handlers
from app.api.kinsun_email_auth import require_kinsun_auth_bff, router
from app.bootstrap.dependencies import (
    get_family_invitation_token_codec,
    get_kinsun_email_challenge_codec,
    get_kinsun_identity_codec,
    get_password_hasher,
)
from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import app as runtime_app
from app.schemas.kinsun_email_auth import (
    CompleteKinsunEmailAuthRequest,
    PasswordLoginRequest,
    StartKinsunEmailAuthRequest,
)
from app.services.kinsun_email_auth_service import RejectedKinsunEmailAuthentication
from app.services.password_auth_service import RejectedPasswordAuthentication

_PASSWORD = "Synthetic-only-password-1"


def _test_app(transaction_state: dict[str, bool]) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(router)
    register_exception_handlers(test_app)

    async def session_dependency():
        try:
            yield SimpleNamespace()
        except Exception:
            transaction_state["rolled_back"] = True
            raise
        else:
            transaction_state["committed"] = True

    test_app.dependency_overrides[require_kinsun_auth_bff] = lambda: None
    test_app.dependency_overrides[get_db_session] = session_dependency
    test_app.dependency_overrides[get_kinsun_identity_codec] = lambda: SimpleNamespace()
    test_app.dependency_overrides[get_kinsun_email_challenge_codec] = lambda: SimpleNamespace()
    test_app.dependency_overrides[get_family_invitation_token_codec] = lambda: SimpleNamespace()
    test_app.dependency_overrides[get_password_hasher] = lambda: SimpleNamespace()
    return test_app


def test_internal_kinsun_auth_router_mount_matches_runtime_gate() -> None:
    private_paths = {route.path for route in router.routes}
    runtime_paths = {route.path for route in runtime_app.routes}

    expected = {
        "/api/v1/internal/auth/kinsun/email/start",
        "/api/v1/internal/auth/kinsun/email/complete",
        "/api/v1/internal/auth/kinsun/password/login",
    }
    assert expected <= private_paths
    assert (
        expected <= runtime_paths
        if get_settings().kinsun_native_auth_enabled
        else not (expected & runtime_paths)
    )


def test_kinsun_auth_request_models_reject_scope_extra_fields_and_bad_secrets() -> None:
    with pytest.raises(ValidationError):
        StartKinsunEmailAuthRequest.model_validate(
            {
                "email": "synthetic.elder@example.test",
                "intent": "ELDER",
                "tenant_id": "10000000-0000-4000-8000-000000000001",
            }
        )
    with pytest.raises(ValidationError):
        CompleteKinsunEmailAuthRequest(
            challenge_token="ke1_" + "a" * 43,
            verification_code="１２３４５６",
            password=_PASSWORD,
        )
    with pytest.raises(ValidationError):
        PasswordLoginRequest(email="synthetic.elder@example.test", password="short")


@pytest.mark.asyncio
async def test_start_returns_uniform_no_store_challenge_without_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"committed": False, "rolled_back": False}

    class Service:
        async def start(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                token="ke1_" + "a" * 43,
                expires_at=datetime(2026, 8, 17, 10, 10, tzinfo=UTC),
            )

    monkeypatch.setattr(api_module, "_service", lambda *args, **kwargs: Service())
    async with AsyncClient(
        transport=ASGITransport(app=_test_app(state)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/internal/auth/kinsun/email/start",
            json={
                "email": "synthetic.elder@example.test",
                "intent": "ELDER",
                "display_name": "合成長者",
            },
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.json()["data"]["status"] == "CHALLENGE_CREATED"
    serialized = json.dumps(response.json(), ensure_ascii=False)
    assert "246810" not in serialized
    assert "synthetic.elder@example.test" not in serialized
    assert state == {"committed": True, "rolled_back": False}


@pytest.mark.asyncio
async def test_wrong_verification_code_returns_canonical_401_and_commits_attempt_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"committed": False, "rolled_back": False}

    class Service:
        async def complete(self, **kwargs):
            del kwargs
            return RejectedKinsunEmailAuthentication()

    monkeypatch.setattr(api_module, "_service", lambda *args, **kwargs: Service())
    async with AsyncClient(
        transport=ASGITransport(app=_test_app(state)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/internal/auth/kinsun/email/complete",
            json={
                "challenge_token": "ke1_" + "a" * 43,
                "verification_code": "000000",
                "password": _PASSWORD,
            },
        )

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["reason_code"] == "AUTHENTICATION_FAILED"
    serialized = json.dumps(response.json())
    assert "000000" not in serialized
    assert _PASSWORD not in serialized
    assert state == {"committed": True, "rolled_back": False}


@pytest.mark.asyncio
async def test_wrong_password_returns_same_canonical_401_and_commits_lockout_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"committed": False, "rolled_back": False}

    class PasswordService:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def authenticate(self, **kwargs):
            del kwargs
            return RejectedPasswordAuthentication()

    monkeypatch.setattr(api_module, "PasswordAuthService", PasswordService)
    async with AsyncClient(
        transport=ASGITransport(app=_test_app(state)),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/internal/auth/kinsun/password/login",
            json={
                "email": "missing.account@example.test",
                "password": _PASSWORD,
            },
        )

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["reason_code"] == "AUTHENTICATION_FAILED"
    serialized = json.dumps(response.json())
    assert "missing.account@example.test" not in serialized
    assert _PASSWORD not in serialized
    assert state == {"committed": True, "rolled_back": False}
