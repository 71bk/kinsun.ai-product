"""Disposable PostgreSQL evidence for exact-visit historical handover."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.domain.deletion import hash_resource_ref, hash_subject_ref
from app.models.actor import Actor
from app.models.care_assignment import CareAssignment
from app.models.care_unit import CareUnit
from app.models.deletion import DeletionRequest, DeletionTombstone
from app.models.membership import ActorTenantMembership
from app.models.service_record import ServiceRecord
from tests.integration.test_identity_api import (
    _build_client_app,
    _prepare_record_completion,
    api_ids,  # noqa: F401 -- shared synthetic fixture
)
from tests.integration.test_identity_api import (
    seed_api_data as _seed_api_data,
)

history_data = _seed_api_data


async def prepare(session, ids):
    current = await _prepare_record_completion(session, ids)
    current.service_scope = ["assignment:read", "service_record:history:read"]
    await session.commit()
    return current


async def source(session, current, *, note="Synthetic previous note", hours=24, **changes):
    # Another real synthetic HOME_CARE_WORKER; no active membership is needed for
    # the historical author. Only the current reader's live grant authorizes access.
    worker = Actor(actor_type="HOME_CARE_WORKER", display_name="Synthetic previous worker")
    session.add(worker)
    await session.flush()
    end = current.service_start - timedelta(hours=hours)
    assignment_values = dict(
        tenant_id=current.tenant_id,
        elder_id=current.elder_id,
        care_unit_id=current.care_unit_id,
        worker_id=worker.id,
        service_start=end - timedelta(hours=2),
        service_end=end,
        status="COMPLETED",
        service_scope=[],
        version=3,
    )
    assignment_values.update(changes.pop("assignment", {}))
    visit = CareAssignment(**assignment_values)
    session.add(visit)
    await session.flush()
    values = dict(
        tenant_id=visit.tenant_id,
        elder_id=visit.elder_id,
        worker_id=visit.worker_id,
        assignment_id=visit.id,
        service_date=visit.service_start.date(),
        service_timezone="UTC",
        record_type="SERVICE_NOTE",
        content={"note": note},
        status="COMPLETED",
        version=1,
        assignment_version=2,
        completed_at=visit.service_start + timedelta(hours=1),
        created_at=visit.service_start + timedelta(hours=1),
    )
    values.update(changes)
    record = ServiceRecord(**values)
    session.add(record)
    await session.flush()
    return visit, record


@pytest.mark.asyncio
async def test_history_handover_order_empty_and_no_old_visit_access(
    test_engine, history_data, committed_session
):
    ids = history_data
    current = await prepare(committed_session, ids)
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    path = f"/api/v1/home-care/assignments/{current.id}/previous-service-record"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        empty = await client.get(path)
        assert empty.status_code == 200 and empty.json()["data"]["record"] is None
        _, older = await source(committed_session, current, hours=48)
        a, first = await source(
            committed_session, current, hours=24, service_timezone="Asia/Taipei"
        )
        b, second = await source(
            committed_session, current, hours=24, service_timezone="Asia/Taipei"
        )
        await committed_session.commit()
        result = await client.get(path)
        expected = max([first, second], key=lambda row: row.service_record_id)
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
        record = result.json()["data"]["record"]
        assert record["service_record_id"] == str(expected.service_record_id)
        assert record["service_record_id"] != str(older.service_record_id)
        assert record["service_timezone"] == "Asia/Taipei"
        assert record["service_date"] == expected.service_date.isoformat()
        assert set(record) == {
            "service_record_id",
            "source_assignment_id",
            "service_date",
            "service_timezone",
            "completed_at",
            "version",
            "content",
        }
        for visit in [a, b]:
            old = await client.get(f"/api/v1/home-care/assignments/{visit.id}/service-record")
            assert old.status_code == 404


@pytest.mark.asyncio
async def test_history_same_worker_retains_recorded_local_day(
    test_engine, history_data, committed_session
):
    ids = history_data
    current = await prepare(committed_session, ids)
    start = current.service_start.replace(hour=16, minute=0, second=0, microsecond=0) - timedelta(
        days=2
    )
    local_day = (start + timedelta(hours=8)).date()
    _, note = await source(
        committed_session,
        current,
        assignment={
            "worker_id": current.worker_id,
            "service_start": start,
            "service_end": start + timedelta(hours=2),
        },
        service_timezone="Asia/Taipei",
        service_date=local_day,
    )
    await committed_session.commit()
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get(
            f"/api/v1/home-care/assignments/{current.id}/previous-service-record"
        )
    assert result.status_code == 200
    record = result.json()["data"]["record"]
    assert record["service_record_id"] == str(note.service_record_id)
    assert record["service_date"] == local_day.isoformat()
    assert record["service_date"] != start.date().isoformat()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        "tenant",
        "elder",
        "unit",
        "IN_PROGRESS",
        "CANCELLED",
        "overlap",
        "future",
        "legacy",
        "worker",
        "record_tenant",
        "record_elder",
        "record_version",
        "late_record",
    ],
)
async def test_history_source_filters(test_engine, history_data, committed_session, invalid):
    ids = history_data
    current = await prepare(committed_session, ids)
    assignment = {}
    record = {}
    hours = 24
    if invalid == "tenant":
        assignment.update(tenant_id=ids["tenant_b_id"], elder_id=ids["elder_3_id"])
    elif invalid == "elder":
        assignment["elder_id"] = ids["elder_1_id"]
    elif invalid == "unit":
        unit = CareUnit(
            tenant_id=ids["tenant_id"], unit_type="DAYCARE_CENTER", name="Synthetic other unit"
        )
        committed_session.add(unit)
        await committed_session.flush()
        assignment["care_unit_id"] = unit.id
    elif invalid in {"IN_PROGRESS", "CANCELLED"}:
        assignment["status"] = invalid
    elif invalid == "overlap":
        hours = -1
    elif invalid == "future":
        hours = -48
    elif invalid == "legacy":
        record.update(version=None, assignment_version=None, tenant_id=None)
    elif invalid == "worker":
        record["worker_id"] = current.worker_id
    elif invalid == "record_tenant":
        record["tenant_id"] = ids["tenant_b_id"]
    elif invalid == "record_elder":
        record["elder_id"] = ids["elder_1_id"]
    elif invalid == "record_version":
        record["assignment_version"] = 3
    elif invalid == "late_record":
        record["completed_at"] = current.service_start
    await source(committed_session, current, assignment=assignment, hours=hours, **record)
    await committed_session.commit()
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get(
            f"/api/v1/home-care/assignments/{current.id}/previous-service-record"
        )
    assert result.status_code == 200 and result.json()["data"]["record"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "denial",
    ["history_scope", "assignment_scope", "completed", "expired", "membership", "worker", "tenant"],
)
async def test_history_live_denial_and_scope_cannot_be_borrowed(
    test_engine, history_data, committed_session, denial
):
    ids = history_data
    current = await prepare(committed_session, ids)
    await source(committed_session, current)
    # Another current assignment has all scopes, but may never lend them to this request.
    other = CareAssignment(
        tenant_id=current.tenant_id,
        elder_id=current.elder_id,
        care_unit_id=current.care_unit_id,
        worker_id=current.worker_id,
        service_start=current.service_start,
        service_end=current.service_end,
        status="IN_PROGRESS",
        service_scope=list(current.service_scope),
        version=1,
    )
    committed_session.add(other)
    await committed_session.commit()
    actor_id, tenant_id = ids["worker_id"], ids["tenant_id"]
    if denial == "history_scope":
        current.service_scope = ["assignment:read", "service_record:read", "summary:read"]
    elif denial == "assignment_scope":
        current.service_scope = ["service_record:history:read"]
    elif denial == "completed":
        current.status = "COMPLETED"
    elif denial == "expired":
        current.service_end = datetime.now(UTC) - timedelta(seconds=1)
    elif denial == "membership":
        membership = await committed_session.scalar(
            select(ActorTenantMembership).where(ActorTenantMembership.actor_id == actor_id)
        )
        membership.effective_to = datetime.now(UTC) - timedelta(seconds=1)
    elif denial == "worker":
        actor_id = ids["daycare_worker_id"]
    elif denial == "tenant":
        tenant_id = ids["tenant_b_id"]
    await committed_session.commit()
    app = _build_client_app(test_engine, actor_id, "HOME_CARE_WORKER", tenant_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get(
            f"/api/v1/home-care/assignments/{current.id}/previous-service-record"
        )
        absent = await client.get(
            f"/api/v1/home-care/assignments/{uuid4()}/previous-service-record"
        )
    assert denied.status_code == absent.status_code == 404
    assert denied.json()["error"]["message"] == absent.json()["error"]["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state", ["REQUESTED", "COMPLETED", "CANCELLED", "tombstone", "other_elder"]
)
async def test_history_deletion_suppresses_retained_notes(
    test_engine, history_data, committed_session, state
):
    ids = history_data
    current = await prepare(committed_session, ids)
    _, note = await source(committed_session, current)
    request = DeletionRequest(
        elder_id=ids["elder_1_id"] if state == "other_elder" else current.elder_id,
        requested_by_actor_id=current.worker_id,
        scope=["MEMORY"],
        status="CANCELLED"
        if state == "tombstone"
        else "REQUESTED"
        if state == "other_elder"
        else state,
    )
    committed_session.add(request)
    await committed_session.flush()
    if state == "tombstone":
        committed_session.add(
            DeletionTombstone(
                tenant_id=current.tenant_id,
                elder_id=current.elder_id,
                deletion_request_id=request.id,
                subject_ref_hash=hash_subject_ref(current.tenant_id, current.elder_id),
                resource_type="SERVICE_RECORD",
                resource_id_hash=hash_resource_ref("SERVICE_RECORD", note.service_record_id),
                policy_version="synthetic-v1",
                reason_code="SYNTHETIC",
                retention_basis="SYNTHETIC_TEST",
            )
        )
    await committed_session.commit()
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get(
            f"/api/v1/home-care/assignments/{current.id}/previous-service-record"
        )
    assert result.status_code == 200
    assert (result.json()["data"]["record"] is not None) == (state in {"CANCELLED", "other_elder"})
