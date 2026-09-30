"""No-DB strict commands and authorization-before-replay boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.database_runtime_principal import (
    RUNTIME_COLUMN_UPDATE_PRIVILEGES,
    RUNTIME_TABLE_PRIVILEGES,
)
from app.schemas.elder_enrollment import EnrollmentCommand
from app.services.elder_enrollment_service import ElderEnrollmentService


def test_runtime_enrollment_permissions_preserve_history_and_ownership():
    assert RUNTIME_TABLE_PRIVILEGES["elder_enrollment_change"] == ("SELECT", "INSERT")
    assert RUNTIME_TABLE_PRIVILEGES["elder_enrollment"] == ("SELECT", "INSERT")
    assert set(RUNTIME_COLUMN_UPDATE_PRIVILEGES["elder_enrollment"]) == {
        "status",
        "version",
        "ended_at",
        "ended_reason",
        "updated_at",
    }


@pytest.mark.parametrize(
    "extra",
    [
        {"reason": " "},
        {"reason": "x" * 121},
        {"expected_version": 0},
        {"expected_version": True},
        {"actor_id": "untrusted"},
        {"status": "ACTIVE"},
    ],
)
def test_strict_enrollment_commands(extra):
    with pytest.raises(ValidationError):
        EnrollmentCommand.model_validate({"expected_version": 1, "reason": "Synthetic", **extra})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role", ["ADMIN", "FAMILY_MEMBER", "ELDER", "HOME_CARE_WORKER", "SYSTEM_SERVICE"]
)
async def test_other_roles_rejected_before_sql(role):
    db = MagicMock()
    service = ElderEnrollmentService(db, ActorContext(uuid4(), role, uuid4()))
    with pytest.raises(NotFoundError):
        await service.get(uuid4())
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_authorization_loss_after_lock_prevents_receipt_or_writes():
    db = MagicMock(execute=AsyncMock())
    service = ElderEnrollmentService(db, ActorContext(uuid4(), "DAYCARE_CARE_WORKER", uuid4()))
    service.authorize = AsyncMock(
        side_effect=[
            (SimpleNamespace(elder_id=uuid4()), "Synthetic", True),
            NotFoundError("Resource not found"),
        ]
    )
    with pytest.raises(NotFoundError):
        await service.command(
            uuid4(), "suspend", EnrollmentCommand(expected_version=1, reason="Test"), "key", "trace"
        )
    assert db.execute.await_count == 2  # Only the two locks, no idempotency SQL.
    db.add.assert_not_called()
