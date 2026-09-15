"""Source-filter contract, forwarding and SQL safety regression."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI

from app.api import care_events
from app.core.auth import ActorContext
from app.repositories.care_event_repo import CareEventRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["MANUAL", "CONVERSATION_SESSION", "UNKNOWN"])
async def test_source_filter_is_forwarded_and_scoped(monkeypatch, source):
    authorize = AsyncMock()
    service = SimpleNamespace(list_for_elder=AsyncMock(return_value=[]))
    monkeypatch.setattr(care_events, "authorize_elder", authorize)
    monkeypatch.setattr(care_events, "CareEventService", MagicMock(return_value=service))
    actor = ActorContext(uuid4(), "HOME_CARE_WORKER", uuid4())
    elder_id = uuid4()
    await care_events.list_care_events(
        elder_id=elder_id,
        event_status=None,
        event_type=None,
        source_type=source,
        date_from=None,
        date_to=None,
        cursor=None,
        limit=2,
        actor_context=actor,
        session=MagicMock(),
    )
    assert authorize.await_args.args[2:] == (elder_id, "care_event:read")
    assert service.list_for_elder.await_args.kwargs["source_type"] == source


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "clause"),
    [
        ("MANUAL", "care_event.source_type ="),
        ("CONVERSATION_SESSION", "care_event.source_session_id IS NOT NULL"),
        ("UNKNOWN", "care_event.source_type IS NULL AND"),
    ],
)
async def test_source_predicate_precedes_limit_with_tenant_elder_scope(source, clause):
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = MagicMock(execute=AsyncMock(return_value=result))
    tenant, elder = uuid4(), uuid4()
    await CareEventRepository(session, tenant).list_for_elder(
        elder_id=elder,
        statuses=["VERIFIED"],
        event_type=None,
        source_type=source,
        event_time_from=None,
        event_time_to=None,
        limit=2,
        cursor=None,
    )
    statement = session.execute.await_args.args[0].compile()
    sql = str(statement)
    assert clause in sql and sql.index(clause) < sql.index("LIMIT")
    assert tenant in statement.params.values() and elder in statement.params.values()
    assert "JOIN" not in sql  # Multiple versions must not multiply timeline rows.


def test_committed_and_live_openapi_source_parameter_match():
    app = FastAPI()
    app.include_router(care_events.router)
    root = Path(__file__).resolve().parents[4]
    committed = json.loads(
        (root / "contracts/openapi/core-api.v1.yaml").read_text(encoding="utf-8")
    )
    path = "/api/v1/elders/{elder_id}/care-events"
    parameters = [
        next(p for p in doc["paths"][path]["get"]["parameters"] if p["name"] == "source_type")
        for doc in (committed, app.openapi())
    ]
    assert parameters[0]["required"] is parameters[1]["required"] is False
    for parameter in parameters:
        assert parameter["schema"]["anyOf"][0]["enum"] == [
            "MANUAL",
            "CONVERSATION_SESSION",
            "UNKNOWN",
        ]
