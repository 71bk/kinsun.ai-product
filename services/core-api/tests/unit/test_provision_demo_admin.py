"""Bootstrap must never repurpose an existing user as an administrator."""

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


@pytest.fixture
def bootstrap(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[4] / "scripts"))
    module = importlib.import_module("provision_demo_admin")
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(kinsun_native_auth_enabled=True)
    )
    monkeypatch.setattr(module, "_repository_head_revision", lambda: "head")
    monkeypatch.setenv("DEMO_ACCOUNT_PASSWORD", "synthetic-admin-password")
    monkeypatch.setattr(
        module,
        "get_kinsun_identity_codec",
        lambda: SimpleNamespace(digest_email=lambda _: "digest", key_version=1),
    )
    hasher = MagicMock()
    monkeypatch.setattr(module, "get_password_hasher", lambda: hasher)
    repo = SimpleNamespace(acquire_subject_lock=AsyncMock(), list_identities_by_subject=AsyncMock())
    monkeypatch.setattr(module, "KinsunIdentityRepository", lambda _: repo)
    session = MagicMock()
    session.scalar = AsyncMock(return_value="head")
    session.get = AsyncMock(return_value=None)
    session.flush = AsyncMock()
    return module, session, repo, hasher


@pytest.mark.asyncio
@pytest.mark.parametrize("role,email_owner", [("ELDER", "same"), ("ADMIN", "other")])
async def test_bootstrap_never_elevates_or_relinks_an_existing_user(bootstrap, role, email_owner):
    module, session, repo, hasher = bootstrap
    session.get.return_value = SimpleNamespace(actor_type=role, email=module.EMAIL)
    repo.list_identities_by_subject.return_value = [
        SimpleNamespace(
            actor_id=module.ACTOR_ID if email_owner == "same" else uuid4(), status="ACTIVE"
        )
    ]
    with pytest.raises(RuntimeError, match="refusing to alter privileges"):
        await module.provision(session)
    session.add.assert_not_called()
    session.add_all.assert_not_called()
    hasher.hash.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_rejects_missing_active_demo_tenant(bootstrap):
    module, session, repo, _ = bootstrap
    repo.list_identities_by_subject.return_value = []
    with pytest.raises(RuntimeError, match="Active demo tenant"):
        await module.provision(session)
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_replay_does_not_reset_credentials(bootstrap, monkeypatch):
    module, session, repo, hasher = bootstrap
    session.get.return_value = SimpleNamespace(actor_type="ADMIN", email=module.EMAIL)
    session.scalar.side_effect = ["head", object()]
    repo.list_identities_by_subject.return_value = [
        SimpleNamespace(actor_id=module.ACTOR_ID, status="ACTIVE")
    ]
    monkeypatch.setattr(
        module,
        "resolve_active_actor_context",
        AsyncMock(return_value=SimpleNamespace(tenant_id=module.TENANT_ID)),
    )
    assert await module.provision(session) is False
    hasher.hash.assert_not_called()
    session.add.assert_not_called()
    session.add_all.assert_not_called()
