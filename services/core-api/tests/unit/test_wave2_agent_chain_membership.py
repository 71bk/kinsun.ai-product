"""Offline ownership and no-renewal checks for the approved QA membership."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[4] / "scripts/qa/wave2_agent_chain_membership.py"
SPEC = importlib.util.spec_from_file_location("wave2_chain_membership", PATH)
assert SPEC and SPEC.loader
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def owned_row(end):
    return dict(
        membership_id=helper.MEMBERSHIP,
        actor_id=helper.STAFF,
        tenant_id=helper.TENANT,
        care_unit_id=helper.UNIT,
        role_code=helper.ROLE,
        effective_to=end,
    )


@pytest.mark.parametrize("command", ["prepare", "expire", "invalid"])
def test_rejects_unapproved_commands(command):
    with pytest.raises(RuntimeError):
        helper.validate_command(command, False)


def test_inspect_needs_no_write_permission():
    helper.validate_command("inspect", False)


@pytest.mark.parametrize(
    "field", ["membership_id", "actor_id", "tenant_id", "care_unit_id", "role_code"]
)
def test_refuses_expiry_of_other_rows(field):
    now = datetime.now(UTC)
    row = owned_row(now + timedelta(hours=4))
    row[field] = "other"
    with pytest.raises(RuntimeError):
        helper.expiry_cutoff(row, now)


@pytest.mark.parametrize("end", [None, "tomorrow", datetime(2026, 9, 8)])
def test_refuses_unbounded_or_naive_expiry(end):
    with pytest.raises(RuntimeError):
        helper.expiry_cutoff(owned_row(end), datetime.now(UTC))


@pytest.mark.parametrize("hours", [-24, 4])
def test_expiry_only_shortens_never_renews(hours):
    now = datetime.now(UTC)
    end = now + timedelta(hours=hours)
    assert helper.expiry_cutoff(owned_row(end), now) == min(end, now - timedelta(seconds=1))


def test_import_has_no_environment_or_database_side_effect():
    assert "get_settings" not in vars(helper)
    assert "create_engine" not in vars(helper)
