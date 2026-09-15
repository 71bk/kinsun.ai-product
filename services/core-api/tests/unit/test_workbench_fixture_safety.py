"""Workbench QA writes are isolated from the retired previous-record campaign."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import NAMESPACE_URL, uuid5

import pytest

path = Path(__file__).resolve().parents[4] / "scripts/qa/workbench_fixture.py"
spec = importlib.util.spec_from_file_location("workbench_fixture_under_test", path)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_campaign_does_not_reuse_retired_ids_or_credentials():
    old_ids = {
        uuid5(NAMESPACE_URL, f"kinsun:previous-record-real-auth-20260914:{key}")
        for key in fixture.base.KEYS
    }
    assert old_ids.isdisjoint(fixture.base.IDS.values())
    assert fixture.base.PRIVATE.name == ".env.workbench-real-auth"


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["prepare", "expire-reader", "retire"])
async def test_write_opt_in_before_any_settings_or_network(monkeypatch, command):
    settings, engine = Mock(), Mock()
    monkeypatch.setattr(fixture.base, "Settings", settings)
    monkeypatch.setattr(fixture.base, "create_async_engine", engine)
    with pytest.raises(RuntimeError):
        await fixture.base.run(command, False)
    settings.assert_not_called()
    engine.assert_not_called()


@pytest.mark.asyncio
async def test_existing_campaign_never_reopened():
    session = SimpleNamespace(get=AsyncMock(return_value=object()), add=Mock())
    with pytest.raises(RuntimeError, match="never overwrite"):
        await fixture.prepare(session, object())
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_confirmed_visit_and_missing_scope_do_not_borrow_permissions(monkeypatch):
    current = SimpleNamespace(status="IN_PROGRESS", version=2)
    restricted = SimpleNamespace(service_scope=["assignment:read", "care_action:read"])
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[current, restricted]), add=Mock(), flush=AsyncMock()
    )
    monkeypatch.setattr(fixture, "original_prepare", AsyncMock())
    await fixture.prepare(session, object())
    assert (current.status, current.version) == ("CONFIRMED", 1)
    assert restricted.service_scope == ["assignment:read"]
    for call in session.add.call_args_list:
        task = call.args[0]
        assert task.tenant_id == fixture.base.IDS["tenant"]
        assert task.elder_id == fixture.base.IDS["elder"]
        assert task.created_by_actor_id == fixture.base.IDS["reader"]
