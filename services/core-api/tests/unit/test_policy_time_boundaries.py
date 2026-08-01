"""Unit tests for ElderAccessPolicy — time boundary edge cases.

Tests verify the semantic behavior at time window boundaries:
- Assignment: service_start <= current_time < service_end (strict <)
- Relationship: effective_from <= current_time AND
  (effective_to IS NULL OR current_time < effective_to)

Since the policy delegates time filtering to repositories, these tests mock the repos:
- Time WITHIN bounds → repository returns a valid entity → policy allows
- Time OUTSIDE bounds → repository returns None → policy denies

Requirements validated: 4.5, 4.6, 7.4, 13.6
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.enums import ActorType
from app.policies.elder_access import (
    ALLOWED,
    NO_VALID_ASSIGNMENT,
    NO_VALID_RELATIONSHIP,
    ElderAccessPolicy,
    ElderAccessRequest,
)

# --- Fixtures ---


@pytest.fixture
def tenant_membership_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_active_membership = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def care_unit_membership_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.is_member = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def care_relationship_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_valid_for_actor = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def care_assignment_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_valid_for_worker = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def policy(
    tenant_membership_repo: AsyncMock,
    care_unit_membership_repo: AsyncMock,
    care_relationship_repo: AsyncMock,
    care_assignment_repo: AsyncMock,
) -> ElderAccessPolicy:
    return ElderAccessPolicy(
        tenant_membership_repo=tenant_membership_repo,
        care_unit_membership_repo=care_unit_membership_repo,
        care_relationship_repo=care_relationship_repo,
        care_assignment_repo=care_assignment_repo,
    )


# --- Test: Assignment Time Boundaries (Requirements 7.4, 13.6) ---


class TestAssignmentTimeBoundaries:
    """Time boundary tests for HOME_CARE_WORKER CareAssignment.

    The repository's find_valid_for_worker applies:
        service_start <= current_time < service_end

    These tests verify that:
    - At exactly service_start → repo returns assignment → policy allows
    - At exactly service_end → repo returns None → policy denies
    - 1s before service_start → repo returns None → policy denies
    """

    async def test_exactly_at_service_start_allowed(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """Assignment at exactly service_start → allowed (inclusive <=)."""
        service_start = datetime(2025, 6, 15, 8, 0, 0, tzinfo=UTC)

        # Repository returns a valid assignment when current_time == service_start
        mock_assignment = MagicMock()
        mock_assignment.id = uuid4()
        mock_assignment.service_scope = ["elder:basic:read"]
        mock_assignment.service_end = datetime(2025, 6, 15, 16, 0, 0, tzinfo=UTC)

        care_assignment_repo.find_valid_for_worker.return_value = mock_assignment

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=service_start,  # exactly at service_start
        )

        decision = await policy.check_access(request)

        assert decision.allowed is True
        assert decision.reason_code == ALLOWED
        assert decision.source_type == "assignment"
        assert decision.source_id == mock_assignment.id

    async def test_exactly_at_service_end_denied(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """Assignment at exactly service_end → denied (strict <)."""
        service_end = datetime(2025, 6, 15, 16, 0, 0, tzinfo=UTC)

        # Repository returns None when current_time == service_end (outside window)
        care_assignment_repo.find_valid_for_worker.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=service_end,  # exactly at service_end → denied
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_ASSIGNMENT

    async def test_one_second_before_service_start_denied(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """Assignment 1s before service_start → denied."""
        service_start = datetime(2025, 6, 15, 8, 0, 0, tzinfo=UTC)
        one_second_before = service_start - timedelta(seconds=1)

        # Repository returns None when current_time < service_start
        care_assignment_repo.find_valid_for_worker.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=one_second_before,  # 1s before service_start
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_ASSIGNMENT


# --- Test: Relationship Time Boundaries (Requirements 4.5, 4.6) ---


class TestRelationshipTimeBoundaries:
    """Time boundary tests for CareRelationship (FAMILY_MEMBER path).

    The repository's find_valid_for_actor applies:
        effective_from <= current_time AND (effective_to IS NULL OR current_time < effective_to)

    These tests verify that:
    - At exactly effective_from → repo returns relationship → policy allows
    - At exactly effective_to → repo returns None → policy denies
    - 1s before effective_from → repo returns None → policy denies
    """

    async def test_exactly_at_effective_from_allowed(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
    ) -> None:
        """Relationship at exactly effective_from → allowed (inclusive <=)."""
        effective_from = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Repository returns a valid relationship when current_time == effective_from
        mock_relationship = MagicMock()
        mock_relationship.id = uuid4()
        mock_relationship.scope = ["elder:basic:read"]
        mock_relationship.effective_to = None  # no expiry

        care_relationship_repo.find_valid_for_actor.return_value = mock_relationship

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=effective_from,  # exactly at effective_from
        )

        decision = await policy.check_access(request)

        assert decision.allowed is True
        assert decision.reason_code == ALLOWED
        assert decision.source_type == "relationship"
        assert decision.source_id == mock_relationship.id

    async def test_exactly_at_effective_to_denied(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
    ) -> None:
        """Relationship at exactly effective_to → denied (strict <)."""
        effective_to = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)

        # Repository returns None when current_time == effective_to (outside window)
        care_relationship_repo.find_valid_for_actor.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=effective_to,  # exactly at effective_to → denied
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_RELATIONSHIP

    async def test_one_second_before_effective_from_denied(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
    ) -> None:
        """Relationship 1s before effective_from → denied."""
        effective_from = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        one_second_before = effective_from - timedelta(seconds=1)

        # Repository returns None when current_time < effective_from
        care_relationship_repo.find_valid_for_actor.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=one_second_before,  # 1s before effective_from
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_RELATIONSHIP
