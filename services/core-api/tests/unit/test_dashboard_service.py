"""Dashboard metadata must never bypass the formal care-action read gate."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.repositories.care_action_repo import CareActionRepository
from app.repositories.care_event_repo import CareEventRepository
from app.repositories.conversation_repo import ConversationRepository, InteractionMetrics
from app.services import dashboard_service


@pytest.mark.asyncio
async def test_identity_route_counts_only_returned_page_and_preserves_cursor(monkeypatch):
    from app.api import identity
    from app.schemas.identity import ElderMode

    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="HOME_CARE_WORKER")
    first, second = uuid4(), uuid4()
    session = AsyncMock()
    service = MagicMock()
    service.get_authorized_elders = AsyncMock(
        side_effect=[
            SimpleNamespace(
                items=[
                    SimpleNamespace(elder_id=elder, display_name="Synthetic", care_unit_name=None)
                ],
                next_cursor=cursor,
                has_more=cursor is not None,
            )
            for elder, cursor in [(first, "next-page"), (second, None)]
        ]
    )
    monkeypatch.setattr(identity, "_build_identity_service", lambda *_: service)
    count = AsyncMock(side_effect=[{first: 105}, {second: 0}])
    monkeypatch.setattr(identity, "get_open_care_action_counts", count)
    review_count = AsyncMock(side_effect=[{first: 103}, {second: 0}])
    monkeypatch.setattr(identity, "get_pending_event_review_counts", review_count)
    metrics = InteractionMetrics(
        3, None, date(2026, 9, 8), "Asia/Taipei", datetime(2026, 9, 8, tzinfo=UTC)
    )
    interaction = AsyncMock(side_effect=[{first: metrics}, {}])
    monkeypatch.setattr(identity, "get_interaction_metrics", interaction)
    for index, (cursor, elder, expected) in enumerate(
        [(None, first, 105), ("next-page", second, 0)]
    ):
        response = await identity.get_authorized_elders(
            mode=ElderMode("home-care"),
            cursor=cursor,
            limit=1,
            actor_context=actor,
            session=session,
        )
        assert response["data"]["items"][0]["open_care_action_count"] == expected
        assert response["data"]["items"][0]["pending_event_review_count"] == (
            103 if index == 0 else 0
        )
        assert review_count.await_args_list[index].args == (session, actor, [elder])
        assert interaction.await_args_list[index].args[:3] == (session, actor, [elder])
        actual = response["data"]["items"][0]["interaction_metrics"]
        assert (actual["today_count"] if actual else None) == (3 if index == 0 else None)
        assert len(response["data"]["items"]) == 1
        assert response["data"]["page"] == {
            "limit": 1,
            "has_more": index == 0,
            "next_cursor": "next-page" if index == 0 else None,
        }
        assert count.await_args_list[index].args == (session, actor, [elder])
        assert service.get_authorized_elders.await_args_list[index].kwargs["cursor"] == cursor


@pytest.mark.asyncio
async def test_counts_only_reauthorized_page_and_preserves_zero(monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="HOME_CARE_WORKER")
    first, denied, empty, unrelated = [uuid4() for _ in range(4)]
    session = AsyncMock()
    auth = AsyncMock(side_effect=[None, NotFoundError("Resource not found"), None])
    count = AsyncMock(return_value={first: 105, unrelated: 99})
    monkeypatch.setattr(dashboard_service, "authorize_elder", auth)
    monkeypatch.setattr(CareActionRepository, "count_open_by_elder", count)
    result = await dashboard_service.get_open_care_action_counts(
        session, actor, [first, denied, empty, first]
    )
    assert result == {first: 105, empty: 0}
    count.assert_awaited_once_with([first, empty])
    assert [c.args[2] for c in auth.await_args_list] == [first, denied, empty]
    assert all(c.args[3] == "care_action:read" for c in auth.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["FAMILY_MEMBER", "ELDER", "ADMIN", "SYSTEM_SERVICE"])
async def test_nonprofessionals_never_query_task_data(role, monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role=role)
    auth = AsyncMock()
    monkeypatch.setattr(dashboard_service, "authorize_elder", auth)
    session = AsyncMock()
    assert await dashboard_service.get_open_care_action_counts(session, actor, [uuid4()]) == {}
    auth.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["FAMILY_MEMBER", "ELDER", "ADMIN", "SYSTEM_SERVICE"])
async def test_nonprofessionals_never_query_event_counts(role, monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role=role)
    auth = AsyncMock()
    monkeypatch.setattr(dashboard_service, "authorize_elder", auth)
    session = AsyncMock()
    assert await dashboard_service.get_pending_event_review_counts(session, actor, [uuid4()]) == {}
    auth.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_event_counts_require_both_scopes_and_deduplicate_page(monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="HOME_CARE_WORKER")
    allowed, read_only, review_only, empty = [uuid4() for _ in range(4)]

    async def authorize(session, actor, elder, scope):
        if (elder == read_only and scope == "care_event:review") or (
            elder == review_only and scope == "care_event:read"
        ):
            raise NotFoundError("Resource not found")

    auth = AsyncMock(side_effect=authorize)
    count = AsyncMock(return_value={allowed: 105, read_only: 9})
    monkeypatch.setattr(dashboard_service, "authorize_elder", auth)
    monkeypatch.setattr(CareEventRepository, "count_pending_review_by_elder", count)
    assert await dashboard_service.get_pending_event_review_counts(
        AsyncMock(), actor, [allowed, read_only, review_only, empty, allowed]
    ) == {allowed: 105, empty: 0}
    count.assert_awaited_once_with([allowed, empty])
    assert [c.args[3] for c in auth.await_args_list[:2]] == ["care_event:read", "care_event:review"]


@pytest.mark.asyncio
async def test_event_count_failure_is_not_zero(monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="DAYCARE_CARE_WORKER")
    monkeypatch.setattr(dashboard_service, "authorize_elder", AsyncMock(return_value=None))
    monkeypatch.setattr(
        CareEventRepository, "count_pending_review_by_elder", AsyncMock(side_effect=RuntimeError)
    )
    with pytest.raises(RuntimeError):
        await dashboard_service.get_pending_event_review_counts(AsyncMock(), actor, [uuid4()])


@pytest.mark.asyncio
async def test_pending_event_sql_is_bounded_and_does_not_count_versions():
    tenant, elder = uuid4(), uuid4()
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [(elder, 105)]
    session.execute.return_value = result
    repo = CareEventRepository(session, tenant)
    assert await repo.count_pending_review_by_elder([]) == {}
    session.execute.assert_not_awaited()
    assert await repo.count_pending_review_by_elder([elder]) == {elder: 105}
    query = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert tenant in query.params.values() and [elder] in query.params.values()
    assert ["CANDIDATE", "NEEDS_REVIEW"] in query.params.values()
    assert "GROUP BY" in str(query) and "count(" in str(query)
    assert all(
        word not in str(query)
        for word in ["JOIN", "LIMIT", "structured_payload", "care_event_version"]
    )


@pytest.mark.asyncio
async def test_dependency_failure_is_not_reported_as_zero(monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="DAYCARE_CARE_WORKER")
    monkeypatch.setattr(dashboard_service, "authorize_elder", AsyncMock(side_effect=RuntimeError))
    with pytest.raises(RuntimeError):
        await dashboard_service.get_open_care_action_counts(AsyncMock(), actor, [uuid4()])


@pytest.mark.asyncio
async def test_group_count_is_tenant_and_page_bounded_without_content_or_provenance():
    tenant, elder = uuid4(), uuid4()
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [(elder, 3)]
    session.execute.return_value = result
    repo = CareActionRepository(session, tenant)
    assert await repo.count_open_by_elder([]) == {}
    session.execute.assert_not_awaited()
    assert await repo.count_open_by_elder([elder]) == {elder: 3}
    query = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert tenant in query.params.values()
    assert [elder] in query.params.values()
    assert ["OPEN", "IN_PROGRESS", "POSTPONED"] in query.params.values()
    sql = str(query)
    assert "GROUP BY" in sql and "count(" in sql
    assert "JOIN" not in sql and "LIMIT" not in sql
    assert "title" not in sql and "provenance" not in sql and "candidate" not in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["FAMILY_MEMBER", "ELDER", "ADMIN", "SYSTEM_SERVICE"])
async def test_nonprofessionals_never_query_interactions(role, monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role=role)
    auth, session = AsyncMock(), AsyncMock()
    monkeypatch.setattr(dashboard_service, "authorize_elder", auth)
    assert (
        await dashboard_service.get_interaction_metrics(
            session, actor, [uuid4()], datetime.now(UTC)
        )
        == {}
    )
    auth.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_interactions_reauthorize_page_without_fabricating_zero(monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="DAYCARE_CARE_WORKER")
    first, denied, gone, unrelated = [uuid4() for _ in range(4)]
    as_of = datetime.now(UTC)
    metrics = InteractionMetrics(0, None, as_of.date(), "UTC", as_of)
    auth = AsyncMock(side_effect=[None, NotFoundError("Resource not found"), None])
    query = AsyncMock(return_value={first: metrics, unrelated: metrics})
    monkeypatch.setattr(dashboard_service, "authorize_elder", auth)
    monkeypatch.setattr(ConversationRepository, "interaction_metrics_by_elder", query)
    assert await dashboard_service.get_interaction_metrics(
        AsyncMock(), actor, [first, denied, gone, first], as_of
    ) == {first: metrics}
    query.assert_awaited_once_with([first, gone], as_of)
    assert all(call.args[3] == "voice_session:read" for call in auth.await_args_list)
    query.side_effect = RuntimeError
    auth.side_effect = None
    with pytest.raises(RuntimeError):
        await dashboard_service.get_interaction_metrics(AsyncMock(), actor, [first], as_of)


@pytest.mark.asyncio
async def test_interaction_sql_uses_snapshot_local_day_and_exists_without_private_content():
    tenant, elder = uuid4(), uuid4()
    as_of = datetime(2026, 9, 8, tzinfo=UTC)
    session, result = AsyncMock(), MagicMock()
    result.all.return_value = [(elder, 0, None, date(2026, 9, 8), "Asia/Taipei")]
    session.execute.return_value = result
    repo = ConversationRepository(session, tenant)
    assert await repo.interaction_metrics_by_elder([], as_of) == {}
    session.execute.assert_not_awaited()
    assert (await repo.interaction_metrics_by_elder([elder], as_of))[elder].today_count == 0
    query = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert tenant in query.params.values() and [elder] in query.params.values()
    assert as_of in query.params.values()
    assert ["SUCCESS", "BLOCKED", "HUMAN_REVIEW"] in query.params.values()
    sql = str(query)
    assert all(
        term in sql
        for term in ["EXISTS", "LEFT OUTER JOIN", "GROUP BY", "timezone(", "FILTER", "max("]
    )
    assert all(
        term not in sql
        for term in ["LIMIT", "transcript", "token_usage", "prompt", "response_body"]
    )
