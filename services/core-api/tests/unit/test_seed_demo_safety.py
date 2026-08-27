"""Safety boundaries for the deterministic demo seed target."""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest


def _load_seed_module() -> ModuleType:
    path = Path(__file__).resolve().parents[4] / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location("seed_demo_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEED_DEMO = _load_seed_module()


def _environment(database_url: str, *, allow_e2e: bool = False) -> dict[str, str]:
    return {
        "APP_ENV": "development",
        "DATABASE_URL": database_url,
        "KINSUN_ALLOW_SYNTHETIC_E2E_SEED": str(allow_e2e).lower(),
    }


def test_default_local_demo_database_is_allowed() -> None:
    value = "postgresql+asyncpg://user:pass@127.0.0.1:5432/kinsun"
    with patch.dict(os.environ, _environment(value), clear=True):
        assert SEED_DEMO._database_url() == value


def test_synthetic_e2e_database_requires_explicit_opt_in() -> None:
    value = "postgresql+asyncpg://user:pass@127.0.0.1:5432/kinsun_frontend_e2e_test"
    with patch.dict(os.environ, _environment(value), clear=True):
        with pytest.raises(RuntimeError, match="KINSUN_ALLOW_SYNTHETIC_E2E_SEED"):
            SEED_DEMO._database_url()

    with patch.dict(os.environ, _environment(value, allow_e2e=True), clear=True):
        assert SEED_DEMO._database_url() == value


def test_remote_database_is_rejected_even_with_e2e_opt_in() -> None:
    value = "postgresql+asyncpg://user:pass@db.example.test/kinsun_frontend_e2e_test"
    with patch.dict(os.environ, _environment(value, allow_e2e=True), clear=True):
        with pytest.raises(RuntimeError, match="restricted to local"):
            SEED_DEMO._database_url()


def test_repository_head_revision_is_discovered_from_alembic_graph() -> None:
    assert SEED_DEMO._repository_head_revision()


@pytest.mark.asyncio
async def test_seed_rejects_database_before_repository_head() -> None:
    session = AsyncMock()
    session.scalar.return_value = "b8d0e4f6a213"

    with patch.object(
        SEED_DEMO,
        "_repository_head_revision",
        return_value="e6f8a0b2c345",
    ):
        with pytest.raises(RuntimeError, match="expected repository head e6f8a0b2c345"):
            await SEED_DEMO._assert_empty_and_current(
                session,
                SEED_DEMO._id("10000000-0000-4000-8000-000000000001"),
            )


@pytest.mark.asyncio
async def test_matching_global_demo_policy_with_safe_metadata_is_reused() -> None:
    existing_id = UUID("81000000-0000-4000-8000-000000000010")
    session = SimpleNamespace(
        scalar=AsyncMock(
            return_value=SimpleNamespace(
                id=existing_id,
                policy_type="CONSENT",
                status="ACTIVE",
                policy_payload={
                    "synthetic_only": True,
                    "purpose_specific": True,
                    "production_approved": False,
                    "supported_purposes": ["BASIC_VOICE"],
                },
            )
        ),
        add=Mock(),
        flush=AsyncMock(),
    )

    result = await SEED_DEMO._get_or_create_demo_policy(
        session,
        approved_by_actor_id=UUID("20000000-0000-4000-8000-000000000013"),
        now=datetime.now(UTC),
    )

    assert result == existing_id
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_incompatible_global_demo_policy_is_rejected() -> None:
    session = SimpleNamespace(
        scalar=AsyncMock(
            return_value=SimpleNamespace(
                id=UUID("81000000-0000-4000-8000-000000000010"),
                policy_type="CONSENT",
                status="ACTIVE",
                policy_payload={"synthetic_only": False},
            )
        ),
        add=Mock(),
        flush=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="incompatible"):
        await SEED_DEMO._get_or_create_demo_policy(
            session,
            approved_by_actor_id=UUID("20000000-0000-4000-8000-000000000013"),
            now=datetime.now(UTC),
        )


def test_demo_manifest_does_not_claim_legacy_memory_is_active() -> None:
    manifest = json.loads(SEED_DEMO.MANIFEST_PATH.read_text(encoding="utf-8"))

    assert "林阿嬤_女兒每週日通話_LEGACY_NEEDS_REVIEW" in manifest["memory"]
    assert "outbox" not in manifest
