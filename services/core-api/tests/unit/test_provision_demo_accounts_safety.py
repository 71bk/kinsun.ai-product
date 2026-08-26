"""Safety boundaries for deterministic Demo login provisioning."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest


def _load_provision_module() -> ModuleType:
    path = Path(__file__).resolve().parents[4] / "scripts" / "provision_demo_accounts.py"
    spec = importlib.util.spec_from_file_location("provision_demo_accounts_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROVISION_DEMO_ACCOUNTS = _load_provision_module()


def test_repository_head_revision_is_discovered_from_alembic_graph() -> None:
    assert PROVISION_DEMO_ACCOUNTS._repository_head_revision()


@pytest.mark.asyncio
async def test_provision_rejects_database_before_repository_head() -> None:
    session = AsyncMock()
    session.scalar.return_value = "b8d0e4f6a213"

    with patch.object(
        PROVISION_DEMO_ACCOUNTS,
        "_repository_head_revision",
        return_value="e6f8a0b2c345",
    ):
        with pytest.raises(RuntimeError, match="expected repository head e6f8a0b2c345"):
            await PROVISION_DEMO_ACCOUNTS._provision(session)
