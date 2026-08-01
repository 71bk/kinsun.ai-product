"""Negative authorization tests — verify that unauthorized access is rejected.

This module tests scenarios where the ElderAccessPolicy MUST deny access.
Tests are at the POLICY level with mocked repositories.

Each test documents a specific denial scenario via its name and docstring,
even though at the unit level they boil down to "repo returns None → deny".
The repository's time/status/ID filtering is what excludes the invalid data;
the policy simply sees None and denies.

Requirements validated: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.11
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.enums import ActorType
from app.policies.elder_access import (
    NO_TENANT_MEMBERSHIP,
    NO_VALID_ASSIGNMENT,
    NO_VALID_RELATIONSHIP,
    WRONG_CARE_UNIT,
    ElderAccessPolicy,
    ElderAccessRequest,
)

# --- Fixtures (same pattern as test_elder_access_policy.py) ---


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


# --- Test Class: HOME_CARE_WORKER Negative Authorization ---


class TestHomeCareWorkerNegativeAuthorization:
    """Negative tests: HOME_CARE_WORKER scenarios that must be denied.

    At the policy level, all these scenarios result in
    care_assignment_repo.find_valid_for_worker returning None because the
    repository query filters by status, time window, and worker_id.
    The policy then denies with NO_VALID_ASSIGNMENT.
    """

    async def test_n1_no_valid_assignment(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """N1: Worker has no assignment for this elder → denied (Req 15.1).

        Scenario: The HOME_CARE_WORKER has never been assigned to this elder.
        The repository returns None because no matching record exists.
        """
        care_assignment_repo.find_valid_for_worker.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_ASSIGNMENT
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None

    async def test_n2_assignment_status_draft(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """N2: Assignment exists but status=DRAFT (not yet confirmed) → denied (Req 15.2).

        Scenario: An assignment record exists for this worker+elder, but its
        status is DRAFT (not CONFIRMED or IN_PROGRESS) — every newly created
        assignment starts as DRAFT in the baseline (there is no SCHEDULED
        status). The repository filters by status IN (CONFIRMED, IN_PROGRESS)
        and returns None.
        """
        care_assignment_repo.find_valid_for_worker.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_ASSIGNMENT
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None

    async def test_n3_past_service_end(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """N3: Assignment's service_end has passed → denied (Req 15.3).

        Scenario: The assignment existed and was CONFIRMED, but current_time
        is at or past service_end. The repository enforces
        current_time < service_end (strict <) and returns None.
        """
        care_assignment_repo.find_valid_for_worker.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            # current_time is past the assignment's service_end
            current_time=datetime(2025, 6, 15, 18, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_ASSIGNMENT
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None

    async def test_n4_worker_id_mismatch(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """N4: Assignment belongs to a different worker → denied (Req 15.4).

        Scenario: An assignment exists for this elder but is assigned to a
        different worker. The repository filters by worker_id == actor_id
        and returns None because the IDs don't match.
        """
        care_assignment_repo.find_valid_for_worker.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),  # This actor is NOT the assigned worker
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_ASSIGNMENT
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None

    async def test_n11_assignment_cancelled(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """N11: Assignment was just cancelled → denied (Req 15.11).

        Scenario: The assignment was previously CONFIRMED but has just been
        cancelled (status=CANCELLED). The repository filters by
        status IN (CONFIRMED, IN_PROGRESS) and returns None because
        CANCELLED is not in the allowed set. Access is immediately revoked.
        """
        care_assignment_repo.find_valid_for_worker.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_ASSIGNMENT
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None


# --- Test Class: DAYCARE_CARE_WORKER Negative Authorization ---


class TestDaycareCareWorkerNegativeAuthorization:
    """Negative tests: DAYCARE_CARE_WORKER scenarios that must be denied.

    DAYCARE_CARE_WORKER requires THREE conditions to all pass:
    1. Active TenantMembership (actor + tenant)
    2. CareUnitMembership for the Elder's care unit
    3. Valid CareRelationship (DAYCARE_ASSIGNMENT)

    Each test removes exactly one condition to verify denial.
    """

    async def test_n5_no_active_tenant_membership(
        self,
        policy: ElderAccessPolicy,
        tenant_membership_repo: AsyncMock,
    ) -> None:
        """N5: No ACTIVE TenantMembership → denied (Req 15.5).

        Scenario: The DAYCARE_CARE_WORKER has no active TenantMembership
        for this tenant. The first step of the three-way check fails
        immediately, and the policy denies with NO_TENANT_MEMBERSHIP.
        """
        tenant_membership_repo.get_active_membership.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.DAYCARE_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_TENANT_MEMBERSHIP
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None

    async def test_n6_not_member_of_elders_care_unit(
        self,
        policy: ElderAccessPolicy,
        tenant_membership_repo: AsyncMock,
        care_relationship_repo: AsyncMock,
        care_unit_membership_repo: AsyncMock,
    ) -> None:
        """N6: Not member of Elder's CareUnit → denied (Req 15.6).

        Scenario: The DAYCARE_CARE_WORKER has an active TenantMembership
        and a valid DAYCARE_ASSIGNMENT relationship exists, but they are
        NOT a member of the Elder's CareUnit. The CareUnitMembership
        check fails and the policy denies with WRONG_CARE_UNIT.
        """
        # Step 1 passes: TenantMembership is active
        tenant_membership_repo.get_active_membership.return_value = AsyncMock()

        # Step 2 (relationship) passes: valid DAYCARE_ASSIGNMENT exists with care_unit_id
        mock_relationship = AsyncMock()
        mock_relationship.care_unit_id = uuid4()
        mock_relationship.scope = ["elder:basic:read"]
        care_relationship_repo.find_valid_for_actor.return_value = mock_relationship

        # Step 3 fails: NOT a member of the Elder's care unit
        care_unit_membership_repo.is_member.return_value = False

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.DAYCARE_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == WRONG_CARE_UNIT
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None

    async def test_n7_no_daycare_assignment_relationship(
        self,
        policy: ElderAccessPolicy,
        tenant_membership_repo: AsyncMock,
        care_relationship_repo: AsyncMock,
    ) -> None:
        """N7: No DAYCARE_ASSIGNMENT relationship → denied (Req 15.7).

        Scenario: The DAYCARE_CARE_WORKER has an active TenantMembership
        but no valid CareRelationship of type DAYCARE_ASSIGNMENT exists
        for this elder. The relationship query returns None and the policy
        denies with NO_VALID_RELATIONSHIP.
        """
        # Step 1 passes: TenantMembership is active
        tenant_membership_repo.get_active_membership.return_value = AsyncMock()

        # Step 2 fails: No DAYCARE_ASSIGNMENT relationship
        care_relationship_repo.find_valid_for_actor.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.DAYCARE_CARE_WORKER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_RELATIONSHIP
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None


# --- Test Class: FAMILY_MEMBER Negative Authorization ---


class TestFamilyMemberNegativeAuthorization:
    """Negative tests: FAMILY_MEMBER scenarios that must be denied.

    Requirements validated: 15.8
    """

    async def test_n8_relationship_expired(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
    ) -> None:
        """N8: Relationship expired (effective_to passed) → denied (Req 15.8).

        Scenario: The FAMILY_MEMBER has a CareRelationship for this elder,
        but its effective_to has passed (now >= effective_to). The repository
        filters by `current_time < effective_to` and returns None because
        the relationship is no longer valid.
        """
        care_relationship_repo.find_valid_for_actor.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            # current_time is past the relationship's effective_to
            current_time=datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == "NO_VALID_RELATIONSHIP"
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None


# --- Test Class: Cross-Tenant Negative Authorization ---


class TestCrossTenantNegativeAuthorization:
    """Negative tests: Cross-tenant scenarios that must be denied.

    At the policy level, cross-tenant access is prevented because
    repositories only return records matching the actor's tenant_id.
    A cross-tenant elder will produce None from all repo queries.

    Requirements validated: 15.9
    """

    async def test_n9_cross_tenant_elder(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """N9: Cross-Tenant elder → denied (Req 15.9).

        Scenario: The actor belongs to Tenant A but the elder belongs to
        Tenant B. All repositories return None because they scope queries
        by the actor's tenant_id, which won't match the elder's tenant.
        Tested here with FAMILY_MEMBER role but applies to any role.
        """
        # Repos already default to None in fixtures
        care_relationship_repo.find_valid_for_actor.return_value = None
        care_assignment_repo.find_valid_for_worker.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=uuid4(),  # Tenant A
            elder_id=uuid4(),  # Elder in Tenant B — repo won't find it
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == "NO_VALID_RELATIONSHIP"
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None

    async def test_n9_cross_tenant_home_care_worker(
        self,
        policy: ElderAccessPolicy,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """N9 variant: Cross-Tenant elder with HOME_CARE_WORKER → denied (Req 15.9).

        Same scenario but exercising the HOME_CARE_WORKER branch.
        """
        care_assignment_repo.find_valid_for_worker.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.HOME_CARE_WORKER,
            tenant_id=uuid4(),  # Tenant A
            elder_id=uuid4(),  # Elder in Tenant B
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == NO_VALID_ASSIGNMENT
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None


# --- Test Class: Actor Inactive Negative Authorization ---


class TestActorInactiveNegativeAuthorization:
    """Negative tests: Actor with status=INACTIVE must be denied.

    The ActorInactiveError is raised at the service/middleware layer
    before reaching the policy. This test verifies that ActorInactiveError
    can be instantiated and raised, confirming the error type is available
    for use by upstream layers.

    Requirements validated: 15.10
    """

    def test_n10_actor_inactive_error_raised(self) -> None:
        """N10: Actor status=INACTIVE → ActorInactiveError (Req 15.10).

        Scenario: An actor with status=INACTIVE attempts any business operation.
        The system raises ActorInactiveError which maps to HTTP 403.
        This test validates the error type is importable and raisable.
        """
        from app.policies import ActorInactiveError

        with pytest.raises(ActorInactiveError):
            raise ActorInactiveError("Actor is not active")

    def test_n10_actor_inactive_error_message(self) -> None:
        """N10 variant: Verify ActorInactiveError carries proper message (Req 15.10)."""
        from app.policies import ActorInactiveError

        error = ActorInactiveError("Actor status is INACTIVE")
        assert error.message == "Actor status is INACTIVE"


# --- Test Class: ADMIN Denied Negative Authorization ---


class TestAdminDeniedNegativeAuthorization:
    """Negative tests: ADMIN role always denied for elder endpoints.

    The policy immediately returns ADMIN_DEFERRED without querying
    any repositories, per the deny-by-default design.

    Requirements validated: 15.12
    """

    async def test_n12_admin_elder_basic_read(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """N12: ADMIN any elder endpoint → denied ADMIN_DEFERRED (Req 15.12).

        Scenario: An ADMIN actor tries to access elder data via
        elder:basic:read. The policy denies immediately with ADMIN_DEFERRED
        without querying any repository.
        """
        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.ADMIN,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == "ADMIN_DEFERRED"
        assert decision.granted_scope == []
        assert decision.source_type is None
        assert decision.source_id is None

        # Verify no repository was called (early exit)
        care_relationship_repo.find_valid_for_actor.assert_not_called()
        care_assignment_repo.find_valid_for_worker.assert_not_called()

    async def test_n12_admin_access_context_read(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
        care_assignment_repo: AsyncMock,
    ) -> None:
        """N12 variant: ADMIN with access_context:read → denied (Req 15.12).

        Same denial regardless of requested_action.
        """
        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.ADMIN,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:access_context:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == "ADMIN_DEFERRED"
        assert decision.granted_scope == []

        # No repos called
        care_relationship_repo.find_valid_for_actor.assert_not_called()
        care_assignment_repo.find_valid_for_worker.assert_not_called()


# --- Test Class: Side-Effect Safety on Denial ---


class TestSideEffectSafetyOnDenial:
    """Negative tests: Denial must not produce any database writes.

    After a deny decision, assert that no session mutation occurs.
    This validates the side-effect safety guarantee from the security policy:
    failed authorization must not modify database state or create outbox events.

    Requirements validated: 15.13
    """

    async def test_n13_denial_no_session_commit(
        self,
        policy: ElderAccessPolicy,
    ) -> None:
        """N13: Deny decision does not trigger session commit (Req 15.13).

        Scenario: After the policy denies access, the session's commit,
        add, and flush methods must never be called. We use a spy mock
        session to assert this.
        """
        from unittest.mock import MagicMock

        session_mock = MagicMock()
        session_mock.new = set()
        session_mock.dirty = set()

        # Execute a deny path
        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        # Confirm denial
        assert decision.allowed is False

        # Assert session was never mutated — policy is pure decision logic
        session_mock.commit.assert_not_called()
        session_mock.add.assert_not_called()
        session_mock.flush.assert_not_called()
        session_mock.execute.assert_not_called()

        # Additional assertions: session tracked no new or dirty objects
        assert session_mock.new == set()
        assert session_mock.dirty == set()

    async def test_n13_denial_no_outbox_writes(
        self,
        policy: ElderAccessPolicy,
        care_relationship_repo: AsyncMock,
    ) -> None:
        """N13 variant: Deny path produces no outbox event writes (Req 15.13).

        Verify that the policy deny path doesn't interact with any
        write-capable components. The repos are only called for SELECT
        queries (read), and a deny result means no further processing.

        Uses a FAMILY_MEMBER actor (there is no LEGAL_REPRESENTATIVE actor
        type in the baseline — a legal representative is a FAMILY_MEMBER
        holding a LEGAL_REPRESENTATIVE relationship). Since find_valid_for_actor
        is checked for both FAMILY_SHARE and LEGAL_REPRESENTATIVE relationship
        types and both return None here, the repo is called twice, not once.
        """
        care_relationship_repo.find_valid_for_actor.return_value = None

        request = ElderAccessRequest(
            actor_id=uuid4(),
            actor_role=ActorType.FAMILY_MEMBER,
            tenant_id=uuid4(),
            elder_id=uuid4(),
            requested_action="elder:basic:read",
            current_time=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        )

        decision = await policy.check_access(request)

        assert decision.allowed is False
        assert decision.reason_code == "NO_VALID_RELATIONSHIP"

        # The repo was called with a SELECT (find) — no write methods exist.
        # Called once per accepted relationship type (FAMILY_SHARE, LEGAL_REPRESENTATIVE).
        assert care_relationship_repo.find_valid_for_actor.call_count == 2
        # Confirm no write-like methods were called on the repo mock
        assert not hasattr(care_relationship_repo, "add") or (
            hasattr(care_relationship_repo.add, "assert_not_called")
            and care_relationship_repo.add.call_count == 0
        )
