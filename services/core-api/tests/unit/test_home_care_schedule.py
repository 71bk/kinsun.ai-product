"""Preview boundary, cursor validation, and bounded SQL projection."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.auth import ActorContext
from app.core.cursor import encode_cursor
from app.core.exceptions import AuthorizationDeniedError, ValidationError
from app.repositories.home_care_schedule_repo import HomeCareScheduleRepository
from app.services.home_care_schedule_service import get_home_care_schedule


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role", ["FAMILY_MEMBER", "DAYCARE_CARE_WORKER", "ELDER", "ADMIN", "SYSTEM_SERVICE"]
)
async def test_other_roles_do_not_query(role):
    session = AsyncMock()
    with pytest.raises(AuthorizationDeniedError):
        await get_home_care_schedule(
            session,
            ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role=role),
            datetime.now(UTC),
            None,
            20,
        )
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", ["bad", encode_cursor(datetime(2026, 9, 9), uuid4())])
async def test_bad_or_naive_cursor_rejected(cursor):
    session = AsyncMock()
    with pytest.raises(ValidationError):
        await get_home_care_schedule(
            session,
            ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="HOME_CARE_WORKER"),
            datetime.now(UTC),
            cursor,
            20,
        )
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_projection_live_filters_and_limit_before_pagination():
    session, result = AsyncMock(), MagicMock()
    session.execute.return_value = result
    result.mappings.return_value.all.return_value = []
    tenant, actor = uuid4(), uuid4()
    now = datetime.now(UTC)
    await HomeCareScheduleRepository(session, tenant).list_today(actor, now, (now, uuid4()), 20)
    stmt = session.execute.await_args.args[0]
    query = stmt.compile(dialect=postgresql.dialect())
    sql = str(query)
    for term in [
        "EXISTS",
        "actor_tenant_membership",
        "care_unit.tenant_id",
        "elder.tenant_id",
        "care_assignment.tenant_id",
        "service_end >",
        "timezone(",
        "LIMIT",
        "@>",
    ]:
        assert term in sql
    assert ["assignment:read", "elder:basic:read"] in query.params.values()
    assert ["CONFIRMED", "IN_PROGRESS"] in query.params.values()
    assert actor in query.params.values() and tenant in query.params.values()
    assert 21 in query.params.values()
    assert {column.key for column in stmt.selected_columns} == {
        "assignment_id",
        "elder_id",
        "display_name",
        "scheduled_start",
        "scheduled_end",
        "status",
        "timezone",
        "local_date",
    }


@pytest.mark.asyncio
async def test_cursor_is_only_position_not_authority(monkeypatch):
    now = datetime.now(UTC)
    row = {"scheduled_start": now, "assignment_id": uuid4()}
    query = AsyncMock(return_value=[row, row])
    monkeypatch.setattr(HomeCareScheduleRepository, "list_today", query)
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="HOME_CARE_WORKER")
    page = await get_home_care_schedule(AsyncMock(), actor, now, None, 1)
    assert page.items == [row] and page.has_more
    query.return_value = []  # cancelled between requests
    page2 = await get_home_care_schedule(AsyncMock(), actor, now, page.next_cursor, 1)
    assert page2.items == [] and not page2.has_more
    query.assert_awaited_with(actor.actor_id, now, (now, row["assignment_id"]), 1)
