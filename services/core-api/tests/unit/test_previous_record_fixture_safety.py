"""Offline safety checks for the isolated real-auth browser campaign."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

path = Path(__file__).resolve().parents[4] / "scripts/qa/previous_record_fixture.py"
spec = importlib.util.spec_from_file_location("previous_record_fixture_under_test", path)
assert spec is not None and spec.loader is not None
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


@pytest.mark.parametrize(
    "command", ["prepare", "add-login-memberships", "expire-reader", "retire", "reset"]
)
@pytest.mark.asyncio
async def test_writes_fail_before_settings_or_connection(monkeypatch, command):
    settings, engine = Mock(), Mock()
    monkeypatch.setattr(fixture, "Settings", settings)
    monkeypatch.setattr(fixture, "create_async_engine", engine)
    with pytest.raises(RuntimeError):
        await fixture.run(command, False)
    settings.assert_not_called()
    engine.assert_not_called()


@pytest.mark.parametrize(
    ("environment", "url"),
    [
        ("production", "postgresql+asyncpg://example.supabase.com/postgres"),
        ("development", "postgresql+asyncpg://localhost/postgres"),
        ("development", "postgresql+asyncpg://example.supabase.com.evil/postgres"),
        ("development", "postgresql+asyncpg://example.supabase.com/another"),
    ],
)
def test_target_refused_without_disclosing_url(environment, url):
    with pytest.raises(RuntimeError) as error:
        fixture.validate_target(environment, url)
    assert url not in str(error.value)


@pytest.mark.asyncio
async def test_prepare_never_overwrites_existing_campaign():
    session = SimpleNamespace(get=AsyncMock(return_value=object()), add=Mock())
    with pytest.raises(RuntimeError, match="never overwrite"):
        await fixture.prepare(session, object())
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_reader_expiry_only_shortens_exact_membership():
    now = datetime.now(UTC)
    tenant = SimpleNamespace(id=fixture.IDS["tenant"], name=fixture.MARKER)
    actor = SimpleNamespace(id=fixture.IDS["reader"], display_name=fixture.MARKER + " reader")
    membership = SimpleNamespace(
        actor_id=actor.id,
        tenant_id=tenant.id,
        care_unit_id=fixture.IDS["unit"],
        effective_from=now - timedelta(days=1),
        effective_to=now + timedelta(hours=4),
    )
    before = vars(membership).copy()
    login_membership = SimpleNamespace(**before)
    login_membership.care_unit_id = None
    login_membership.role_code = "HOME_CARE_WORKER"
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[tenant, actor, membership, login_membership] * 2)
    )
    await fixture.retire(session, reader_only=True)
    first = membership.effective_to
    assert first <= datetime.now(UTC)
    assert login_membership.effective_to == first
    await fixture.retire(session, reader_only=True)
    assert membership.effective_to == first
    assert login_membership.effective_to == first
    assert {k: v for k, v in vars(membership).items() if k != "effective_to"} == {
        k: v for k, v in before.items() if k != "effective_to"
    }
    assert [call.args[1] for call in session.get.call_args_list[:4]] == [
        fixture.IDS[key]
        for key in ("tenant", "reader", "reader_membership", "reader_login_membership")
    ]


@pytest.mark.asyncio
async def test_reader_expiry_refuses_foreign_membership():
    membership = SimpleNamespace(actor_id="different-actor")
    session = SimpleNamespace(
        get=AsyncMock(
            side_effect=[
                SimpleNamespace(id=fixture.IDS["tenant"], name=fixture.MARKER),
                SimpleNamespace(id=fixture.IDS["reader"], display_name=fixture.MARKER + " reader"),
                membership,
            ]
        )
    )
    with pytest.raises(RuntimeError, match="ownership mismatch"):
        await fixture.retire(session, reader_only=True)
    assert vars(membership) == {"actor_id": "different-actor"}


@pytest.mark.asyncio
async def test_login_memberships_are_bounded_by_existing_unit_expiry():
    now = datetime.now(UTC)
    expiry = now + timedelta(hours=1)
    rows = [SimpleNamespace(id=fixture.IDS["tenant"], name=fixture.MARKER)]
    for who in ("writer", "reader"):
        rows.extend(
            [
                SimpleNamespace(
                    id=fixture.IDS[who],
                    display_name=fixture.MARKER + " " + who,
                    actor_type="HOME_CARE_WORKER",
                    status="ACTIVE",
                ),
                SimpleNamespace(
                    actor_id=fixture.IDS[who],
                    tenant_id=fixture.IDS["tenant"],
                    care_unit_id=fixture.IDS["unit"],
                    role_code="HOME_CARE_WORKER",
                    effective_from=now - timedelta(days=1),
                    effective_to=expiry,
                ),
                None,
            ]
        )
    session = SimpleNamespace(get=AsyncMock(side_effect=rows), add=Mock(), flush=AsyncMock())
    await fixture.add_login_memberships(session)
    assert session.add.call_count == 2
    for call, who in zip(session.add.call_args_list, ("writer", "reader"), strict=True):
        membership = call.args[0]
        assert membership.id == fixture.IDS[who + "_login_membership"]
        assert membership.actor_id == fixture.IDS[who]
        assert membership.care_unit_id is None
        assert now <= membership.effective_from < expiry
        assert membership.effective_to == expiry
