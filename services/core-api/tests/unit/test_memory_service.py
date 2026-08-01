"""Fail-closed confirmation authority tests for long-term memory."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.middleware.auth import ActorContext
from app.services.memory_service import MemoryService


@pytest.mark.asyncio
async def test_voice_confirmation_is_rejected_before_any_repository_access() -> None:
    session = MagicMock()
    service = MemoryService(session, uuid4())
    memory = SimpleNamespace(elder_id=uuid4())
    actor = ActorContext(
        actor_id=uuid4(),
        actor_role="ELDER",
        tenant_id=uuid4(),
    )
    request = SimpleNamespace(confirmation_method="VOICE")

    with pytest.raises(ValidationError) as exc_info:
        await service._validate_confirmation_authority(
            memory=memory,
            actor_context=actor,
            request=request,
        )

    assert exc_info.value.details[0]["field"] == "confirmation_method"
    session.scalar.assert_not_called()
    session.execute.assert_not_called()
