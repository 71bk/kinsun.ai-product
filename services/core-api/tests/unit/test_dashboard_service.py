"""Dashboard metadata must never bypass the formal care-action read gate."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.repositories.care_action_repo import CareActionRepository
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
