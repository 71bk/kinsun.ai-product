"""Unit tests for ElderAccessPolicy — basic logic, role allow/deny paths, scope checking.

Tests cover:
- Deny by default (no relationship/assignment data)
- Each role allow path (FAMILY_MEMBER via FAMILY_SHARE, FAMILY_MEMBER via
  LEGAL_REPRESENTATIVE, HOME_CARE_WORKER, DAYCARE_CARE_WORKER)
- ADMIN deny (deferred), unknown role deny
- Scope checking (action in/not in scope, empty scope)

Note there is no LEGAL_REPRESENTATIVE actor type in the baseline — being a
legal representative is a CareRelationship type held by a FAMILY_MEMBER
actor (see app/policies/elder_access.py module docstring). Tests that used
to authenticate as ActorType.LEGAL_REPRESENTATIVE now authenticate as
ActorType.FAMILY_MEMBER while keeping the LEGAL_REPRESENTATIVE relationship
type, preserving the original intent (a legal representative can read the
elder).

Requirements validated: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.enums import ActorType, RelationshipType
from app.policies.elder_access import (
    ADMIN_DEFERRED,
    ALLOWED,
    NO_TENANT_MEMBERSHIP,
    NO_VALID_ASSIGNMENT,
    NO_VALID_RELATIONSHIP,
    NOT_ELDER_SELF,
    SCOPE_INSUFFICIENT,
    UNKNOWN_ROLE,
    WRONG_CARE_UNIT,
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


@pytest.fixture
def base_request() -> ElderAccessRequest:
    """A basic access request — role can be overridden per test."""
    return ElderAccessRequest(
        actor_id=uuid4(),
        actor_role=ActorType.FAMILY_MEMBER,
        tenant_id=uuid4(),
        elder_id=uuid4(),
        requested_action="elder:basic:read",
        current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
    )


# --- Test: Deny by Default (Requirement 7.1) ---


class TestDenyByDefault:
    """When no relationship or assignment exists, policy must deny."""

    async def test_family_member_no_relationship(
        self, policy: ElderAccessPolicy, base_request: ElderAccessRequest
    ) -> None:
        """FAMILY_MEMBER with no valid relationship → denied."""
        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action=base_request.requested_action,
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_RELATIONSHIP
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None

    async def test_home_care_worker_no_assignment(
        self, policy: ElderAccessPolicy, base_request: ElderAccessRequest
    ) -> None:
        """HOME_CARE_WORKER with no valid assignment → denied."""
        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action=base_request.requested_action,
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_ASSIGNMENT

    async def test_daycare_worker_no_tenant_membership(
        self, policy: ElderAccessPolicy, base_request: ElderAccessRequest
    ) -> None:
        """DAYCARE_CARE_WORKER with no tenant membership → denied."""
        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.DAYCARE_CARE_WORKER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action=base_request.requested_action,
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_TENANT_MEMBERSHIP


class TestElderSelfAccess:
    async def test_linked_elder_actor_is_allowed(
        self, policy: ElderAccessPolicy, base_request: ElderAccessRequest
    ) -> None:
        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.ELDER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="voice_session:create",
            current_time=base_request.current_time,
            actor_is_elder_self=True,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is True
        assert decision.source_type == "elder_self"
        assert decision.source_id == base_request.elder_id
        assert decision.granted_scope == ["voice_session:create"]

    @pytest.mark.parametrize("action", ["care_event:review", "summary:review"])
    async def test_linked_elder_actor_cannot_use_caregiver_review_scope(
        self,
        policy: ElderAccessPolicy,
        base_request: ElderAccessRequest,
        action: str,
    ) -> None:
        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.ELDER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action=action,
            current_time=base_request.current_time,
            actor_is_elder_self=True,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == SCOPE_INSUFFICIENT
        assert decision.granted_scope == []

    async def test_unlinked_elder_actor_is_denied(
        self, policy: ElderAccessPolicy, base_request: ElderAccessRequest
    ) -> None:
        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.ELDER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="voice_session:create",
            current_time=base_request.current_time,
            actor_is_elder_self=False,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NOT_ELDER_SELF


class TestSystemServiceAccess:
    async def test_service_requires_membership_relationship_and_scope(
        self,
        policy: ElderAccessPolicy,
        tenant_membership_repo: AsyncMock,
        care_relationship_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        tenant_membership_repo.get_active_membership.return_value = MagicMock()
        relationship = MagicMock()
        relationship.id = uuid4()
        relationship.scope = ["assignment:create"]
        relationship.effective_to = None
        care_relationship_repo.find_valid_for_actor.return_value = relationship
        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.SYSTEM_SERVICE,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="assignment:create",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is True
        assert decision.source_id == relationship.id
        care_relationship_repo.find_valid_for_actor.assert_awaited_once_with(
            actor_id=request.actor_id,
            elder_id=request.elder_id,
            relationship_type=RelationshipType.HOME_CARE_ASSIGNMENT.value,
            current_time=request.current_time,
        )

    async def test_service_without_tenant_membership_is_denied(
        self, policy: ElderAccessPolicy, base_request: ElderAccessRequest
    ) -> None:
        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.SYSTEM_SERVICE,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="assignment:create",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_TENANT_MEMBERSHIP


# --- Test: FAMILY_MEMBER Allow Path (Requirement 7.2) ---


class TestFamilyMemberAllowPath:
    """FAMILY_MEMBER with valid FAMILY_SHARE relationship and action in scope → allowed."""

    async def test_allowed_with_valid_relationship(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        """Valid relationship with requested_action in scope → ALLOWED."""
        mock_relationship = MagicMock()
        mock_relationship.id = uuid4()
        mock_relationship.scope = ["elder:basic:read", "elder:access_context:read"]
        mock_relationship.effective_to = None

        care_relationship_repo.find_valid_for_actor.return_value = mock_relationship

        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is True
        assert decision.reason_code == ALLOWED
        assert decision.granted_scope == ["elder:basic:read", "elder:access_context:read"]
        assert decision.source_type == "relationship"
        assert decision.source_id == mock_relationship.id
        assert decision.expires_at is None


# --- Test: LEGAL_REPRESENTATIVE Allow Path (Requirement 7.3) ---


class TestLegalRepresentativeAllowPath:
    """FAMILY_MEMBER holding a LEGAL_REPRESENTATIVE relationship → allowed.

    There is no LEGAL_REPRESENTATIVE actor type in the baseline; a legal
    representative authenticates as FAMILY_MEMBER and holds a
    RelationshipType.LEGAL_REPRESENTATIVE CareRelationship. The fake
    repository only returns a relationship for the LEGAL_REPRESENTATIVE
    type (None for FAMILY_SHARE) so the test genuinely exercises the second
    branch of the two-relationship-type check, not the first.
    """

    async def test_allowed_with_valid_relationship(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        """Valid LEGAL_REPRESENTATIVE relationship → ALLOWED."""
        mock_relationship = MagicMock()
        mock_relationship.id = uuid4()
        mock_relationship.scope = ["elder:basic:read", "elder:sensitive:read"]
        mock_relationship.effective_to = datetime(2026, 12, 31, tzinfo=UTC)

        async def find_valid_for_actor(*, relationship_type, **kwargs):
            if relationship_type == RelationshipType.LEGAL_REPRESENTATIVE.value:
                return mock_relationship
            return None

        care_relationship_repo.find_valid_for_actor.side_effect = find_valid_for_actor

        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is True
        assert decision.reason_code == ALLOWED
        assert decision.source_type == "relationship"
        assert decision.source_id == mock_relationship.id
        assert decision.expires_at == datetime(2026, 12, 31, tzinfo=UTC)


# --- Test: HOME_CARE_WORKER Allow Path (Requirement 7.4) ---


class TestHomeCareWorkerAllowPath:
    """HOME_CARE_WORKER with valid assignment and action in service_scope → allowed."""

    async def test_allowed_with_valid_assignment(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        """Valid assignment with requested_action in service_scope → ALLOWED."""
        mock_assignment = MagicMock()
        mock_assignment.id = uuid4()
        mock_assignment.service_scope = ["elder:basic:read"]
        mock_assignment.service_end = datetime(2025, 12, 31, tzinfo=UTC)

        care_assignment_repo.find_valid_for_worker.return_value = mock_assignment

        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is True
        assert decision.reason_code == ALLOWED
        assert decision.granted_scope == ["elder:basic:read"]
        assert decision.source_type == "assignment"
        assert decision.source_id == mock_assignment.id
        assert decision.expires_at == datetime(2025, 12, 31, tzinfo=UTC)


# --- Test: DAYCARE_CARE_WORKER Allow Path (Requirement 7.5) ---


class TestDaycareCareWorkerAllowPath:
    """DAYCARE_CARE_WORKER with all three conditions met → allowed."""

    async def test_allowed_with_full_three_way_verification(
        self,
        policy: ElderAccessPolicy,
        tenant_membership_repo: AsyncMock,
        care_unit_membership_repo: AsyncMock,
        care_relationship_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        """TenantMembership + CareRelationship + CareUnitMembership → ALLOWED."""
        # Step 1: Active tenant membership
        mock_membership = MagicMock()
        tenant_membership_repo.get_active_membership.return_value = mock_membership

        # Step 2: Valid DAYCARE_ASSIGNMENT relationship
        mock_relationship = MagicMock()
        mock_relationship.id = uuid4()
        mock_relationship.scope = ["elder:basic:read", "elder:access_context:read"]
        mock_relationship.effective_to = None
        mock_relationship.care_unit_id = uuid4()
        care_relationship_repo.find_valid_for_actor.return_value = mock_relationship

        # Step 3: Actor is member of the care unit
        care_unit_membership_repo.is_member.return_value = True

        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.DAYCARE_CARE_WORKER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is True
        assert decision.reason_code == ALLOWED
        assert decision.source_type == "relationship"
        assert decision.source_id == mock_relationship.id
        assert decision.granted_scope == ["elder:basic:read", "elder:access_context:read"]

    async def test_denied_no_care_unit_membership(
        self,
        policy: ElderAccessPolicy,
        tenant_membership_repo: AsyncMock,
        care_unit_membership_repo: AsyncMock,
        care_relationship_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        """TenantMembership OK + CareRelationship OK + NOT in care unit → WRONG_CARE_UNIT."""
        mock_membership = MagicMock()
        tenant_membership_repo.get_active_membership.return_value = mock_membership

        mock_relationship = MagicMock()
        mock_relationship.id = uuid4()
        mock_relationship.scope = ["elder:basic:read"]
        mock_relationship.effective_to = None
        mock_relationship.care_unit_id = uuid4()
        care_relationship_repo.find_valid_for_actor.return_value = mock_relationship

        # Not a member of the care unit
        care_unit_membership_repo.is_member.return_value = False

        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.DAYCARE_CARE_WORKER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == WRONG_CARE_UNIT

    async def test_denied_no_relationship(
        self,
        policy: ElderAccessPolicy,
        tenant_membership_repo: AsyncMock,
        care_relationship_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        """TenantMembership OK but no DAYCARE_ASSIGNMENT → NO_VALID_RELATIONSHIP."""
        mock_membership = MagicMock()
        tenant_membership_repo.get_active_membership.return_value = mock_membership

        # No relationship found
        care_relationship_repo.find_valid_for_actor.return_value = None

        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.DAYCARE_CARE_WORKER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_RELATIONSHIP


# --- Test: ADMIN Deny (Requirement 7.6) ---


class TestAdminDeny:
    """ADMIN role is always deferred (denied)."""

    async def test_admin_always_denied(
        self, policy: ElderAccessPolicy, base_request: ElderAccessRequest
    ) -> None:
        """Any request with role=ADMIN → ADMIN_DEFERRED."""
        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.ADMIN,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == ADMIN_DEFERRED
        assert decision.granted_scope == []
        assert decision.source_type is None


# --- Test: Unknown Role Deny (Requirement 7.6) ---


class TestUnknownRoleDeny:
    """Unknown roles are always denied."""

    async def test_unknown_role_denied(
        self, policy: ElderAccessPolicy, base_request: ElderAccessRequest
    ) -> None:
        """Unrecognized role string → UNKNOWN_ROLE."""
        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role="UNKNOWN_ROLE_XYZ",
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == UNKNOWN_ROLE
        assert decision.granted_scope == []
        assert decision.source_type is None


# --- Test: Scope Checking (Requirements 7.2, 7.3, 7.4) ---


class TestScopeChecking:
    """Scope checking — action must be in scope for access to be granted."""

    async def test_action_not_in_scope(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        """Relationship found but requested_action NOT in scope → SCOPE_INSUFFICIENT."""
        mock_relationship = MagicMock()
        mock_relationship.id = uuid4()
        mock_relationship.scope = ["elder:access_context:read"]  # doesn't include basic:read
        mock_relationship.effective_to = None

        care_relationship_repo.find_valid_for_actor.return_value = mock_relationship

        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",  # not in scope
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == SCOPE_INSUFFICIENT

    async def test_empty_scope(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        """Relationship found but scope is empty list → SCOPE_INSUFFICIENT."""
        mock_relationship = MagicMock()
        mock_relationship.id = uuid4()
        mock_relationship.scope = []
        mock_relationship.effective_to = None

        care_relationship_repo.find_valid_for_actor.return_value = mock_relationship

        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == SCOPE_INSUFFICIENT

    async def test_assignment_action_not_in_service_scope(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        """Assignment found but requested_action NOT in service_scope → SCOPE_INSUFFICIENT."""
        mock_assignment = MagicMock()
        mock_assignment.id = uuid4()
        mock_assignment.service_scope = ["elder:sensitive:read"]  # doesn't include basic:read
        mock_assignment.service_end = datetime(2025, 12, 31, tzinfo=UTC)

        care_assignment_repo.find_valid_for_worker.return_value = mock_assignment

        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == SCOPE_INSUFFICIENT

    async def test_assignment_empty_service_scope(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
        base_request: ElderAccessRequest,
    ) -> None:
        """Assignment found but service_scope is empty → SCOPE_INSUFFICIENT."""
        mock_assignment = MagicMock()
        mock_assignment.id = uuid4()
        mock_assignment.service_scope = []
        mock_assignment.service_end = datetime(2025, 12, 31, tzinfo=UTC)

        care_assignment_repo.find_valid_for_worker.return_value = mock_assignment

        request = ElderAccessRequest(
            actor_id=base_request.actor_id,
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=base_request.tenant_id,
            elder_id=base_request.elder_id,
            requested_action="elder:basic:read",
            current_time=base_request.current_time,
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == SCOPE_INSUFFICIENT
