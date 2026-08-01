"""Unit tests for TenantMembershipRepository.

Tests the repository logic using a mocked async session.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.tenant_membership_repo import TenantMembershipRepository


class TestTenantMembershipRepositoryInit:
    """Tests for TenantMembershipRepository constructor."""

    def test_accepts_session(self) -> None:
        """Constructor stores the session."""
        session = AsyncMock()
        repo = TenantMembershipRepository(session)
        assert repo._session is session


class TestGetActiveMembership:
    """Tests for TenantMembershipRepository.get_active_membership."""

    @pytest.mark.asyncio
    async def test_returns_membership_when_found(self) -> None:
        """Returns TenantMembership when an active record exists."""
        session = AsyncMock()
        repo = TenantMembershipRepository(session)

        expected = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected
        session.execute.return_value = mock_result

        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        result = await repo.get_active_membership(actor_id, tenant_id)

        assert result is expected
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        """Returns None when no active membership exists."""
        session = AsyncMock()
        repo = TenantMembershipRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        result = await repo.get_active_membership(actor_id, tenant_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_passes_actor_id_and_tenant_id_to_query(self) -> None:
        """Verifies that actor_id and tenant_id are used in the query."""
        session = AsyncMock()
        repo = TenantMembershipRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        actor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        await repo.get_active_membership(actor_id, tenant_id)

        # Verify execute was called (query construction tested via integration)
        session.execute.assert_called_once()
        call_args = session.execute.call_args
        # The first positional argument is the select statement
        stmt = call_args[0][0]
        # Compile to string to verify WHERE clause contains expected filters
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "actor_tenant_membership" in compiled
        assert "actor_id" in compiled
        assert "tenant_id" in compiled
        assert "status" in compiled
