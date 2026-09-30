"""No-DB strict commands, role gate, and authorization-after-wait regression."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.schemas.elder_profile import CreateCareProfileRequest, UpdateElderProfileRequest
from app.services.elder_profile_service import ElderProfileService


@pytest.mark.parametrize(
    "field,value",
    [
        ("content", " "),
        ("content", "x" * 501),
        ("reason", " "),
        ("reason", "x" * 201),
        ("category", "DIAGNOSIS"),
        ("verification_status", "VERIFIED"),
        ("source_actor_id", str(uuid4())),
    ],
)
def test_care_commands_reject_untrusted_or_unbounded_fields(field, value):
    with pytest.raises(ValidationError):
        CreateCareProfileRequest.model_validate(
            {"category": "ALLERGY", "content": "Synthetic", "reason": "Correction", field: value}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["ADMIN", "FAMILY_MEMBER", "ELDER", "SYSTEM_SERVICE"])
async def test_non_staff_fails_before_db_access(role):
    session = MagicMock()
    service = ElderProfileService(session, ActorContext(uuid4(), role, uuid4()))
    with pytest.raises(NotFoundError):
        await service.authorize(uuid4(), "elder:basic:read")
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_scope_loss_while_waiting_for_elder_lock_prevents_idempotency_and_writes():
    session = MagicMock()
    service = ElderProfileService(session, ActorContext(uuid4(), "DAYCARE_CARE_WORKER", uuid4()))
    service.authorize = AsyncMock(side_effect=[None, NotFoundError("Resource not found")])
    service._elder = AsyncMock(return_value=SimpleNamespace(profile_version=1))
    body = UpdateElderProfileRequest(
        display_name="Synthetic",
        preferred_name=None,
        preferred_language="ZH_TW",
        expected_version=1,
        reason="Correction",
    )
    with pytest.raises(NotFoundError):
        await service.mutate(uuid4(), body, operation="BASIC_UPDATED", key="test", trace_id="test")
    session.execute.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_stale_actor_role_and_inactive_actor_fail_closed():
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    service = ElderProfileService(session, ActorContext(uuid4(), "DAYCARE_CARE_WORKER", uuid4()))
    with pytest.raises(NotFoundError):
        await service.profile(uuid4())
