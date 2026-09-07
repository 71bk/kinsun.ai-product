"""Offline guards for the opt-in manual browser fixture; never connect to a DB."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

fixture_path = Path(__file__).resolve().parents[4] / "scripts/qa/wave2_browser_fixture.py"
spec = importlib.util.spec_from_file_location("wave2_browser_fixture_under_test", fixture_path)
assert spec is not None and spec.loader is not None
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


@pytest.mark.parametrize("command", ["prepare", "expire", "reset", "delete", ""])
@pytest.mark.asyncio
async def test_unapproved_commands_fail_before_env_or_connection(monkeypatch, command):
    load_env = Mock()
    engine = Mock()
    monkeypatch.setattr(fixture, "Settings", load_env)
    monkeypatch.setattr(fixture, "create_async_engine", engine)
    with pytest.raises(RuntimeError):
        await fixture.main(SimpleNamespace(command=command, allow_synthetic_write=False))
    load_env.assert_not_called()
    engine.assert_not_called()


def test_inspect_is_allowed_without_write_opt_in():
    fixture.validate_command("inspect", False)


@pytest.mark.parametrize("command", ["reset", "delete", "truncate"])
def test_unknown_commands_rejected_even_with_opt_in(command):
    with pytest.raises(RuntimeError):
        fixture.validate_command(command, True)


@pytest.mark.parametrize(
    ("environment", "url"),
    [
        ("production", "postgresql+asyncpg://example.supabase.com/postgres"),
        ("test", "postgresql+asyncpg://example.supabase.com/postgres"),
        ("development", "postgresql+asyncpg://localhost/postgres"),
        ("development", "postgresql+asyncpg://example.supabase.com.evil/postgres"),
        ("development", "postgresql+asyncpg://example.supabase.com/another"),
        ("development", "https://example.supabase.com/postgres"),
    ],
)
def test_target_guards_do_not_echo_connection_values(environment, url):
    with pytest.raises(RuntimeError) as error:
        fixture.validate_target(environment, url)
    assert url not in str(error.value)


def test_expected_development_target_is_allowed():
    fixture.validate_target("development", "postgresql+asyncpg://example.supabase.com/postgres")


def owned_rows():
    expiry = datetime.now(UTC) + timedelta(hours=4)
    return [
        SimpleNamespace(name=fixture.MARKER, tenant_id=fixture.TENANT),
        SimpleNamespace(
            display_name=f"{fixture.MARKER} elder",
            tenant_id=fixture.TENANT,
            primary_care_unit_id=fixture.IDS["unit"],
        ),
        SimpleNamespace(
            elder_id=fixture.IDS["elder"],
            actor_id=fixture.STAFF,
            care_unit_id=fixture.IDS["unit"],
            tenant_id=fixture.TENANT,
            relationship_type="DAYCARE_ASSIGNMENT",
            effective_to=expiry,
        ),
        SimpleNamespace(
            actor_id=fixture.STAFF,
            care_unit_id=fixture.IDS["unit"],
            tenant_id=fixture.TENANT,
            role_code="DAYCARE_CARE_WORKER",
            effective_to=expiry,
        ),
    ]


@pytest.mark.parametrize(
    ("index", "field"),
    [
        (0, "name"),
        (0, "tenant_id"),
        (1, "display_name"),
        (1, "tenant_id"),
        (1, "primary_care_unit_id"),
        (2, "elder_id"),
        (2, "actor_id"),
        (2, "care_unit_id"),
        (2, "tenant_id"),
        (2, "relationship_type"),
        (3, "actor_id"),
        (3, "care_unit_id"),
        (3, "tenant_id"),
        (3, "role_code"),
    ],
)
@pytest.mark.asyncio
async def test_expiry_refuses_ownership_mismatch_without_changes(index, field):
    rows = owned_rows()
    setattr(rows[index], field, uuid4())
    before = [vars(row).copy() for row in rows]
    session = SimpleNamespace(get=AsyncMock(side_effect=rows))
    with pytest.raises(RuntimeError, match="ownership mismatch"):
        await fixture.expire(session)
    assert [vars(row) for row in rows] == before


@pytest.mark.asyncio
async def test_expiry_only_shortens_the_two_exact_authorizations():
    rows = owned_rows()
    before = [vars(row).copy() for row in rows]
    session = SimpleNamespace(get=AsyncMock(side_effect=rows * 2))
    await fixture.expire(session)
    for index, row in enumerate(rows):
        if index < 2:
            assert vars(row) == before[index]
        else:
            assert row.effective_to < datetime.now(UTC)
            assert {k: v for k, v in vars(row).items() if k != "effective_to"} == {
                k: v for k, v in before[index].items() if k != "effective_to"
            }
    first = [row.effective_to for row in rows[2:]]
    await fixture.expire(session)
    assert [row.effective_to for row in rows[2:]] == first
    assert [call.args[1] for call in session.get.call_args_list[:4]] == [
        fixture.IDS[key] for key in ("unit", "elder", "relationship", "membership")
    ]


@pytest.mark.asyncio
async def test_existing_fixture_is_never_overwritten(monkeypatch):
    monkeypatch.setattr(fixture, "assert_owner", AsyncMock())
    session = SimpleNamespace(get=AsyncMock(return_value=object()), add=Mock())
    with pytest.raises(RuntimeError, match="already exists"):
        await fixture.prepare(session)
    session.add.assert_not_called()
