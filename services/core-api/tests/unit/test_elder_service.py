"""Unit tests for ElderService — non-disclosure pattern verification.

Tests that ElderService correctly implements:
- get_elder_if_authorized: returns Elder when authorized, None otherwise
- get_access_context: returns AccessContext when authorized, None otherwise
- Non-disclosure: unauthorized and nonexistent both return None
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.elder import Elder
from app.policies.elder_access import (
    ALLOWED,
    NO_VALID_RELATIONSHIP,
    ElderAccessDecision,
    ElderAccessPolicy,
    ElderAccessRequest,
)
from app.services.elder_service import AccessContext, ElderService

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_elder_repo() -> AsyncMock:
    """Provide a mock ElderRepository."""
    repo = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.exists = AsyncMock()
    return repo


@pytest.fixture
def mock_policy() -> AsyncMock:
    """Provide a mock ElderAccessPolicy."""
    policy = AsyncMock(spec=ElderAccessPolicy)
    policy.check_access = AsyncMock()
    return policy


@pytest.fixture
def elder_service(mock_elder_repo: AsyncMock, mock_policy: AsyncMock) -> ElderService:
    """Provide an ElderService with mocked dependencies."""
    return ElderService(
        elder_repo=mock_elder_repo,
        elder_access_policy=mock_policy,
    )


@pytest.fixture
def sample_elder() -> MagicMock:
    """Provide a sample Elder entity."""
    elder = MagicMock(spec=Elder)
    elder.id = uuid4()
    elder.tenant_id = uuid4()
    elder.display_name = "Test Elder"
    elder.primary_care_setting = "DAYCARE"
    elder.status = "ACTIVE"
    return elder


@pytest.fixture
def sample_access_request(sample_elder: MagicMock) -> ElderAccessRequest:
    """Provide a sample ElderAccessRequest."""
    return ElderAccessRequest(
        actor_id=uuid4(),
        actor_role="FAMILY_MEMBER",
        tenant_id=sample_elder.tenant_id,
        elder_id=sample_elder.id,
        requested_action="elder:basic:read",
        current_time=datetime.now(UTC),
    )


def _allowed_decision() -> ElderAccessDecision:
    """Create an allowed decision with typical values."""
    return ElderAccessDecision(
        allowed=True,
        reason_code=ALLOWED,
        expires_at=None,
        granted_scope=["elder:basic:read", "elder:access_context:read"],
        source_type="relationship",
        source_id=uuid4(),
    )


def _denied_decision(reason: str = NO_VALID_RELATIONSHIP) -> ElderAccessDecision:
    """Create a denied decision."""
    return ElderAccessDecision(
        allowed=False,
        reason_code=reason,
        expires_at=None,
        granted_scope=[],
        source_type=None,
        source_id=None,
    )


# ─── get_elder_if_authorized Tests ──────────────────────────────────────────


class TestGetElderIfAuthorized:
    """Tests for ElderService.get_elder_if_authorized."""

    async def test_returns_elder_when_exists_and_authorized(
        self,
        elder_service: ElderService,
        mock_elder_repo: AsyncMock,
        mock_policy: AsyncMock,
        sample_elder: MagicMock,
        sample_access_request: ElderAccessRequest,
    ) -> None:
        """Elder exists and policy allows → return the Elder entity."""
        mock_elder_repo.get_by_id.return_value = sample_elder
        mock_policy.check_access.return_value = _allowed_decision()

        result = await elder_service.get_elder_if_authorized(sample_access_request)

        assert result is sample_elder
        mock_elder_repo.get_by_id.assert_awaited_once_with(sample_access_request.elder_id)
        mock_policy.check_access.assert_awaited_once_with(sample_access_request)

    async def test_returns_none_when_elder_not_found(
        self,
        elder_service: ElderService,
        mock_elder_repo: AsyncMock,
        mock_policy: AsyncMock,
        sample_access_request: ElderAccessRequest,
    ) -> None:
        """Elder doesn't exist → return None without calling policy."""
        mock_elder_repo.get_by_id.return_value = None

        result = await elder_service.get_elder_if_authorized(sample_access_request)

        assert result is None
        mock_elder_repo.get_by_id.assert_awaited_once()
        mock_policy.check_access.assert_not_awaited()

    async def test_returns_none_when_unauthorized(
        self,
        elder_service: ElderService,
        mock_elder_repo: AsyncMock,
        mock_policy: AsyncMock,
        sample_elder: MagicMock,
        sample_access_request: ElderAccessRequest,
    ) -> None:
        """Elder exists but policy denies → return None (non-disclosure)."""
        mock_elder_repo.get_by_id.return_value = sample_elder
        mock_policy.check_access.return_value = _denied_decision()

        result = await elder_service.get_elder_if_authorized(sample_access_request)

        assert result is None
        mock_elder_repo.get_by_id.assert_awaited_once()
        mock_policy.check_access.assert_awaited_once()

    async def test_non_disclosure_both_paths_return_none(
        self,
        elder_service: ElderService,
        mock_elder_repo: AsyncMock,
        mock_policy: AsyncMock,
        sample_elder: MagicMock,
        sample_access_request: ElderAccessRequest,
    ) -> None:
        """Non-disclosure: nonexistent and unauthorized both return None."""
        # Path 1: Elder doesn't exist
        mock_elder_repo.get_by_id.return_value = None
        result_not_found = await elder_service.get_elder_if_authorized(sample_access_request)

        # Path 2: Elder exists but unauthorized
        mock_elder_repo.get_by_id.return_value = sample_elder
        mock_policy.check_access.return_value = _denied_decision()
        result_unauthorized = await elder_service.get_elder_if_authorized(sample_access_request)

        # Both return None — handler can't distinguish
        assert result_not_found is None
        assert result_unauthorized is None


# ─── get_access_context Tests ────────────────────────────────────────────────


class TestGetAccessContext:
    """Tests for ElderService.get_access_context."""

    async def test_returns_access_context_when_authorized(
        self,
        elder_service: ElderService,
        mock_elder_repo: AsyncMock,
        mock_policy: AsyncMock,
        sample_access_request: ElderAccessRequest,
    ) -> None:
        """Elder exists and policy allows → return AccessContext."""
        mock_elder_repo.exists.return_value = True
        mock_policy.check_access.return_value = _allowed_decision()

        result = await elder_service.get_access_context(sample_access_request)

        assert result is not None
        assert isinstance(result, AccessContext)
        assert result.purpose == "elder_care_access"
        assert result.allowed_actions == ["elder:basic:read", "elder:access_context:read"]
        assert result.source_type == "relationship"
        assert result.expires_at is None
        mock_elder_repo.exists.assert_awaited_once_with(sample_access_request.elder_id)
        mock_policy.check_access.assert_awaited_once_with(sample_access_request)

    async def test_returns_none_when_elder_not_found(
        self,
        elder_service: ElderService,
        mock_elder_repo: AsyncMock,
        mock_policy: AsyncMock,
        sample_access_request: ElderAccessRequest,
    ) -> None:
        """Elder doesn't exist → return None without calling policy."""
        mock_elder_repo.exists.return_value = False

        result = await elder_service.get_access_context(sample_access_request)

        assert result is None
        mock_elder_repo.exists.assert_awaited_once()
        mock_policy.check_access.assert_not_awaited()

    async def test_returns_none_when_unauthorized(
        self,
        elder_service: ElderService,
        mock_elder_repo: AsyncMock,
        mock_policy: AsyncMock,
        sample_access_request: ElderAccessRequest,
    ) -> None:
        """Elder exists but policy denies → return None (non-disclosure)."""
        mock_elder_repo.exists.return_value = True
        mock_policy.check_access.return_value = _denied_decision()

        result = await elder_service.get_access_context(sample_access_request)

        assert result is None
        mock_elder_repo.exists.assert_awaited_once()
        mock_policy.check_access.assert_awaited_once()

    async def test_access_context_with_expiry(
        self,
        elder_service: ElderService,
        mock_elder_repo: AsyncMock,
        mock_policy: AsyncMock,
        sample_access_request: ElderAccessRequest,
    ) -> None:
        """AccessContext includes expires_at from the decision."""
        expiry = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)
        decision = ElderAccessDecision(
            allowed=True,
            reason_code=ALLOWED,
            expires_at=expiry,
            granted_scope=["elder:basic:read"],
            source_type="assignment",
            source_id=uuid4(),
        )
        mock_elder_repo.exists.return_value = True
        mock_policy.check_access.return_value = decision

        result = await elder_service.get_access_context(sample_access_request)

        assert result is not None
        assert result.expires_at == expiry
        assert result.source_type == "assignment"
        assert result.allowed_actions == ["elder:basic:read"]

    async def test_source_summary_for_relationship(
        self,
        elder_service: ElderService,
        mock_elder_repo: AsyncMock,
        mock_policy: AsyncMock,
        sample_access_request: ElderAccessRequest,
    ) -> None:
        """Source summary correctly built for relationship authorization."""
        decision = ElderAccessDecision(
            allowed=True,
            reason_code=ALLOWED,
            expires_at=None,
            granted_scope=["elder:basic:read"],
            source_type="relationship",
            source_id=uuid4(),
        )
        mock_elder_repo.exists.return_value = True
        mock_policy.check_access.return_value = decision

        result = await elder_service.get_access_context(sample_access_request)

        assert result is not None
        assert "relationship" in result.source_summary

    async def test_source_summary_for_assignment(
        self,
        elder_service: ElderService,
        mock_elder_repo: AsyncMock,
        mock_policy: AsyncMock,
        sample_access_request: ElderAccessRequest,
    ) -> None:
        """Source summary correctly built for assignment authorization."""
        decision = ElderAccessDecision(
            allowed=True,
            reason_code=ALLOWED,
            expires_at=None,
            granted_scope=["elder:basic:read"],
            source_type="assignment",
            source_id=uuid4(),
        )
        mock_elder_repo.exists.return_value = True
        mock_policy.check_access.return_value = decision

        result = await elder_service.get_access_context(sample_access_request)

        assert result is not None
        assert "assignment" in result.source_summary
