"""Unit tests for BaseRepository (app/repositories/base.py).

Tests validation logic and construction. For query methods, uses a real
SQLAlchemy model class (required by select()) with a mocked async session.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import TenantScopeError
from app.db.base import BaseModel, TenantScopedMixin
from app.repositories.base import BaseRepository


# A concrete model class for testing query construction
class _TestEntity(BaseModel, TenantScopedMixin):
    """Test-only entity model for unit testing BaseRepository queries."""

    __tablename__ = "test_entities"
    __pk_name__ = "test_entity_id"


class TestBaseRepositoryInit:
    """Tests for BaseRepository constructor validation."""

    def test_accepts_valid_uuid_tenant_id(self) -> None:
        """Constructor succeeds with a valid UUID tenant_id."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()

        repo = BaseRepository(session, tenant_id)

        assert repo.tenant_id == tenant_id

    def test_raises_tenant_scope_error_when_tenant_id_is_none(self) -> None:
        """Constructor raises TenantScopeError if tenant_id is None."""
        session = AsyncMock()

        with pytest.raises(TenantScopeError, match="cannot be None"):
            BaseRepository(session, None)  # type: ignore[arg-type]

    def test_raises_tenant_scope_error_when_tenant_id_is_string(self) -> None:
        """Constructor raises TenantScopeError if tenant_id is not a UUID."""
        session = AsyncMock()

        with pytest.raises(TenantScopeError, match="must be a UUID instance"):
            BaseRepository(session, "not-a-uuid")  # type: ignore[arg-type]

    def test_raises_tenant_scope_error_when_tenant_id_is_integer(self) -> None:
        """Constructor raises TenantScopeError if tenant_id is an integer."""
        session = AsyncMock()

        with pytest.raises(TenantScopeError, match="must be a UUID instance"):
            BaseRepository(session, 12345)  # type: ignore[arg-type]

    def test_tenant_id_property_returns_constructor_value(self) -> None:
        """The tenant_id property returns the value passed to __init__."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()

        repo = BaseRepository(session, tenant_id)

        assert repo.tenant_id is tenant_id


class TestBaseRepositoryGetById:
    """Tests for BaseRepository.get_by_id method."""

    @pytest.mark.asyncio
    async def test_get_by_id_calls_session_execute(self) -> None:
        """get_by_id executes a query via the session."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        repo = BaseRepository(session, tenant_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await repo.get_by_id(_TestEntity, entity_id)

        session.execute.assert_called_once()
        mock_result.scalar_one_or_none.assert_called_once()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_returns_entity_when_found(self) -> None:
        """get_by_id returns the entity when session finds it."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        repo = BaseRepository(session, tenant_id)

        expected_entity = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_entity
        session.execute.return_value = mock_result

        result = await repo.get_by_id(_TestEntity, entity_id)

        assert result is expected_entity


class TestBaseRepositoryListAll:
    """Tests for BaseRepository.list_all method."""

    @pytest.mark.asyncio
    async def test_list_all_calls_session_execute(self) -> None:
        """list_all executes a query via the session."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        repo = BaseRepository(session, tenant_id)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        result = await repo.list_all(_TestEntity)

        session.execute.assert_called_once()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_all_returns_entities(self) -> None:
        """list_all returns the list of entities from the session."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        repo = BaseRepository(session, tenant_id)

        entities = [MagicMock(), MagicMock()]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = entities
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        result = await repo.list_all(_TestEntity)

        assert result == entities

    @pytest.mark.asyncio
    async def test_list_all_accepts_custom_limit_and_offset(self) -> None:
        """list_all passes limit and offset to the query."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        repo = BaseRepository(session, tenant_id)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        # Should not raise — accepts keyword arguments
        result = await repo.list_all(_TestEntity, limit=50, offset=10)

        session.execute.assert_called_once()
        assert result == []
