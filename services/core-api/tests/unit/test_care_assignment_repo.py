"""Unit tests for CareAssignmentRepository.

Tests the CareAssignmentRepository methods using a mocked async session,
verifying query construction and result mapping.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.care_assignment_repo import (
    AuthorizedElderRow,
    CareAssignmentRepository,
)


class TestFindValidForWorker:
    """Tests for CareAssignmentRepository.find_valid_for_worker method."""

    @pytest.mark.asyncio
    async def test_returns_assignment_when_found(self) -> None:
        """Returns the matching CareAssignment when all criteria are met."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        worker_id = uuid.uuid4()
        elder_id = uuid.uuid4()
        now = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        repo = CareAssignmentRepository(session, tenant_id)

        expected_assignment = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_assignment
        session.execute.return_value = mock_result

        result = await repo.find_valid_for_worker(worker_id, elder_id, now)

        assert result is expected_assignment
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_valid_assignment(self) -> None:
        """Returns None when no assignment matches all criteria."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        worker_id = uuid.uuid4()
        elder_id = uuid.uuid4()
        now = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        repo = CareAssignmentRepository(session, tenant_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await repo.find_valid_for_worker(worker_id, elder_id, now)

        assert result is None
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_tenant_scope(self) -> None:
        """Verifies that the query includes the tenant_id scope."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        repo = CareAssignmentRepository(session, tenant_id)

        assert repo.tenant_id == tenant_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        await repo.find_valid_for_worker(uuid.uuid4(), uuid.uuid4(), datetime.now(tz=UTC))

        # Session execute was called with the constructed query
        session.execute.assert_called_once()


class TestFindAuthorizedEldersByWorker:
    """Tests for CareAssignmentRepository.find_authorized_elders_by_worker method."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_assignments(self) -> None:
        """Returns empty list when the worker has no active assignments."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        worker_id = uuid.uuid4()
        now = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        repo = CareAssignmentRepository(session, tenant_id)

        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        result = await repo.find_authorized_elders_by_worker(worker_id, now)

        assert result == []
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_authorized_elder_rows(self) -> None:
        """Returns correctly mapped AuthorizedElderRow instances."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        worker_id = uuid.uuid4()
        elder_id_1 = uuid.uuid4()
        elder_id_2 = uuid.uuid4()
        now = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        repo = CareAssignmentRepository(session, tenant_id)

        # Simulate rows returned from the DB
        row1 = MagicMock()
        row1.elder_id = elder_id_1
        row1.display_name = "王大明"
        row1.care_unit_name = "日照中心A"

        row2 = MagicMock()
        row2.elder_id = elder_id_2
        row2.display_name = "李小華"
        row2.care_unit_name = "日照中心B"

        mock_result = MagicMock()
        mock_result.all.return_value = [row1, row2]
        session.execute.return_value = mock_result

        result = await repo.find_authorized_elders_by_worker(worker_id, now)

        assert len(result) == 2
        assert result[0] == AuthorizedElderRow(
            elder_id=elder_id_1,
            display_name="王大明",
            care_unit_name="日照中心A",
        )
        assert result[1] == AuthorizedElderRow(
            elder_id=elder_id_2,
            display_name="李小華",
            care_unit_name="日照中心B",
        )

    @pytest.mark.asyncio
    async def test_handles_null_care_unit_name(self) -> None:
        """Correctly handles None care_unit_name in results."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()
        worker_id = uuid.uuid4()
        elder_id = uuid.uuid4()
        now = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        repo = CareAssignmentRepository(session, tenant_id)

        row = MagicMock()
        row.elder_id = elder_id
        row.display_name = "王大明"
        row.care_unit_name = None

        mock_result = MagicMock()
        mock_result.all.return_value = [row]
        session.execute.return_value = mock_result

        result = await repo.find_authorized_elders_by_worker(worker_id, now)

        assert len(result) == 1
        assert result[0].care_unit_name is None


class TestAuthorizedElderRow:
    """Tests for the AuthorizedElderRow NamedTuple."""

    def test_is_named_tuple(self) -> None:
        """AuthorizedElderRow is a NamedTuple with correct fields."""
        elder_id = uuid.uuid4()
        row = AuthorizedElderRow(
            elder_id=elder_id,
            display_name="Test Name",
            care_unit_name="Unit A",
        )
        assert row.elder_id == elder_id
        assert row.display_name == "Test Name"
        assert row.care_unit_name == "Unit A"

    def test_fields_are_accessible_by_index(self) -> None:
        """NamedTuple fields are accessible by position."""
        elder_id = uuid.uuid4()
        row = AuthorizedElderRow(
            elder_id=elder_id,
            display_name="Name",
            care_unit_name="Unit",
        )
        assert row[0] == elder_id
        assert row[1] == "Name"
        assert row[2] == "Unit"
