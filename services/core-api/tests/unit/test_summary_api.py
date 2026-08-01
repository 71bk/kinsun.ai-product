"""Daily-summary API formal-read safety tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from app.api import summaries
from app.core.exceptions import NotFoundError
from app.middleware.auth import ActorContext


def _actor() -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role="DAYCARE_CARE_WORKER",
        tenant_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_list_summaries_defaults_to_formal_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock()
    service = SimpleNamespace(list_for_date=AsyncMock(return_value=[]))
    monkeypatch.setattr(summaries, "authorize_elder", authorize)
    monkeypatch.setattr(summaries, "SummaryService", MagicMock(return_value=service))

    await summaries.list_summaries(
        elder_id=elder_id,
        summary_date=None,
        summary_status=None,
        actor_context=actor,
        session=session,
    )

    authorize.assert_awaited_once_with(session, actor, elder_id, "summary:read")
    service.list_for_date.assert_awaited_once_with(
        elder_id=elder_id,
        summary_date=None,
        statuses=list(summaries.FORMAL_SUMMARY_STATUSES),
    )


@pytest.mark.asyncio
async def test_list_summaries_requires_review_scope_for_non_formal_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock()
    service = SimpleNamespace(list_for_date=AsyncMock(return_value=[]))
    monkeypatch.setattr(summaries, "authorize_elder", authorize)
    monkeypatch.setattr(summaries, "SummaryService", MagicMock(return_value=service))

    await summaries.list_summaries(
        elder_id=elder_id,
        summary_date=None,
        summary_status=["NEEDS_REVIEW"],
        actor_context=actor,
        session=session,
    )

    assert authorize.await_args_list == [
        call(session, actor, elder_id, "summary:read"),
        call(session, actor, elder_id, "summary:review"),
    ]
    service.list_for_date.assert_awaited_once_with(
        elder_id=elder_id,
        summary_date=None,
        statuses=["NEEDS_REVIEW"],
    )


@pytest.mark.asyncio
async def test_get_summary_does_not_read_non_formal_summary_before_review_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    summary_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock(
        side_effect=[None, NotFoundError("Resource not found")],
    )
    service = SimpleNamespace(get=AsyncMock(return_value=None))
    monkeypatch.setattr(summaries, "authorize_elder", authorize)
    monkeypatch.setattr(summaries, "SummaryService", MagicMock(return_value=service))

    with pytest.raises(NotFoundError):
        await summaries.get_summary(
            elder_id=elder_id,
            summary_id=summary_id,
            actor_context=actor,
            session=session,
        )

    assert authorize.await_args_list == [
        call(session, actor, elder_id, "summary:read"),
        call(session, actor, elder_id, "summary:review"),
    ]
    service.get.assert_awaited_once_with(
        elder_id,
        summary_id,
        statuses=list(summaries.FORMAL_SUMMARY_STATUSES),
    )


@pytest.mark.asyncio
async def test_get_summary_reviewer_fallback_is_limited_to_known_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    summary_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock()
    service = SimpleNamespace(get=AsyncMock(side_effect=[None, None]))
    monkeypatch.setattr(summaries, "authorize_elder", authorize)
    monkeypatch.setattr(summaries, "SummaryService", MagicMock(return_value=service))

    with pytest.raises(NotFoundError):
        await summaries.get_summary(
            elder_id=elder_id,
            summary_id=summary_id,
            actor_context=actor,
            session=session,
        )

    assert service.get.await_args_list == [
        call(
            elder_id,
            summary_id,
            statuses=list(summaries.FORMAL_SUMMARY_STATUSES),
        ),
        call(
            elder_id,
            summary_id,
            statuses=list(summaries.ALLOWED_SUMMARY_STATUSES),
        ),
    ]
