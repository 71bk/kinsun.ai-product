"""Offline checks for the opt-in B03/B04 campaign's write boundaries."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

path = Path(__file__).resolve().parents[4] / "scripts/qa/event_review_fixture.py"
spec = importlib.util.spec_from_file_location("event_fixture_under_test", path)
assert spec is not None and spec.loader is not None
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


@pytest.mark.parametrize("command", ["prepare", "expire", "retire"])
def test_writes_require_opt_in_before_reading_settings(monkeypatch, command):
    settings, engine = Mock(), Mock()
    monkeypatch.setattr(fixture, "Settings", settings)
    monkeypatch.setattr(fixture, "create_engine", engine)
    monkeypatch.setattr(fixture.sys, "argv", ["fixture", command, "--env-file", "unused"])
    with pytest.raises(RuntimeError, match="opt-in"):
        fixture.main()
    settings.assert_not_called()
    engine.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_env": "production"},
        {"database_url": "postgresql+asyncpg://localhost/postgres"},
        {"database_url": "postgresql+asyncpg://example.supabase.com.evil/postgres"},
        {"database_url": "postgresql+asyncpg://example.supabase.com/another"},
        {"fake_auth_enabled": True},
        {"app_session_auth_enabled": False},
    ],
)
def test_non_development_or_fake_auth_target_is_refused(overrides):
    settings = dict(
        app_env="development",
        database_url="postgresql+asyncpg://example.supabase.com/postgres",
        kinsun_native_auth_enabled=True,
        app_session_auth_enabled=True,
        fake_auth_enabled=False,
    )
    settings.update(overrides)
    with pytest.raises(RuntimeError) as error:
        fixture.validate_target(SimpleNamespace(**settings))
    assert settings["database_url"] not in str(error.value)


@pytest.mark.parametrize("private_exists", [True, False])
def test_prepare_cannot_replace_campaign_or_private_bootstrap(monkeypatch, private_exists):
    monkeypatch.setattr(fixture, "PRIVATE", SimpleNamespace(exists=lambda: private_exists))
    session = SimpleNamespace(get=Mock(return_value=object()), add=Mock(), add_all=Mock())
    with pytest.raises(RuntimeError, match="never overwrite"):
        fixture.prepare(session, object())
    session.add.assert_not_called()
    session.add_all.assert_not_called()


def ownership_rows():
    now = datetime.now(UTC)
    tenant = SimpleNamespace(id=fixture.IDS["tenant"], name=fixture.MARKER)
    actor = SimpleNamespace(
        id=fixture.IDS["worker"],
        actor_type=fixture.ROLE,
        display_name=fixture.MARKER + " worker",
    )
    relation = SimpleNamespace(
        actor_id=actor.id,
        tenant_id=tenant.id,
        elder_id=fixture.IDS["elder"],
        care_unit_id=fixture.IDS["unit"],
        effective_from=now - timedelta(minutes=1),
        effective_to=now + timedelta(hours=1),
    )
    return tenant, actor, relation


def test_expiry_only_shortens_exact_relationship_and_is_idempotent():
    rows = ownership_rows()
    before = vars(rows[2]).copy()
    session = SimpleNamespace(get=Mock(side_effect=[*rows, *rows]))
    fixture.expire(session)
    first = rows[2].effective_to
    fixture.expire(session)
    assert rows[2].effective_to == first <= datetime.now(UTC)
    assert {k: v for k, v in vars(rows[2]).items() if k != "effective_to"} == {
        k: v for k, v in before.items() if k != "effective_to"
    }
    assert len(session.get.call_args_list) == 6


def test_foreign_relationship_cannot_be_expired():
    rows = ownership_rows()
    rows[2].elder_id = fixture.IDS["unassigned"]
    before = vars(rows[2]).copy()
    session = SimpleNamespace(get=Mock(side_effect=rows))
    with pytest.raises(RuntimeError, match="ownership mismatch"):
        fixture.expire(session)
    assert vars(rows[2]) == before
