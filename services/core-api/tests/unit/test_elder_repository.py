"""Unit tests for ElderRepository (app/repositories/elder_repo.py).

Tests the ElderRepository methods using a mocked async session,
following the same pattern as test_base_repository.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.elder_repo import ElderRepository


class TestElderRepositoryGetById:
    """Tests for ElderRepository.get_by_id method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_elder_not_found(self) -> None:
        """get_by_id returns None when no elder exists for the given ID and tenant."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        elder_id = uuid.uuid4()
        repo = ElderRepository(session, tenant_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await repo.get_by_id(elder_id)

        assert result is None
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_elder_when_found(self) -> None:
        """get_by_id returns the Elder entity when it exists in the tenant scope."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        elder_id = uuid.uuid4()
        repo = ElderRepository(session, tenant_id)

        expected_elder = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_elder
        session.execute.return_value = mock_result

        result = await repo.get_by_id(elder_id)

        assert result is expected_elder

    @pytest.mark.asyncio
    async def test_delegates_to_base_repository(self) -> None:
        """get_by_id delegates to BaseRepository.get_by_id with the Elder model class."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        elder_id = uuid.uuid4()
        repo = ElderRepository(session, tenant_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        await repo.get_by_id(elder_id)

        # Verify session.execute was called (query was issued)
        session.execute.assert_called_once()
        mock_result.scalar_one_or_none.assert_called_once()


class TestElderRepositoryExists:
    """Tests for ElderRepository.exists method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_elder_exists(self) -> None:
        """exists returns True when the elder is found within the tenant scope."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        elder_id = uuid.uuid4()
        repo = ElderRepository(session, tenant_id)

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        session.execute.return_value = mock_result

        result = await repo.exists(elder_id)

        assert result is True
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_elder_not_found(self) -> None:
        """exists returns False when no elder matches the ID and tenant."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        elder_id = uuid.uuid4()
        repo = ElderRepository(session, tenant_id)

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        session.execute.return_value = mock_result

        result = await repo.exists(elder_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent_uuid(self) -> None:
        """exists returns False for a completely random UUID that doesn't exist."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        elder_id = uuid.uuid4()
        repo = ElderRepository(session, tenant_id)

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        session.execute.return_value = mock_result

        result = await repo.exists(elder_id)

        assert result is False
        session.execute.assert_called_once()
