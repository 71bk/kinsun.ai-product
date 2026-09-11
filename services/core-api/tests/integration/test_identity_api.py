"""Integration tests for Identity and Elder API endpoints.

Tests the full HTTP request/response cycle via AsyncClient with a real
database (PostgreSQL via Docker). Uses FakeAuthenticator to inject known
ActorContext values.

Validates:
- GET /api/v1/me returns correct actor info (Req 10.1)
- GET /api/v1/me/authorized-elders for various modes (Req 10.1, 11.1)
- GET /api/v1/elders/{elder_id} authorized and non-authorized paths (Req 12.1, 12.2, 12.3)
- GET /api/v1/elders/{elder_id}/access-context complete flow (Req 11.1)
- Non-disclosure: not-found vs unauthorized responses are identical (Req 14.1, 14.2)

Requirements: 10.1, 11.1, 12.1, 12.2, 12.3, 14.1, 14.2
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_db_engine
from app.main import create_app
from app.middleware.auth import FakeAuthenticator, get_authenticator
from app.models.actor import Actor
from app.models.agent import AgentRun
from app.models.care_action import CareAction
from app.models.care_assignment import CareAssignment
from app.models.care_event import CareEvent
from app.models.care_relationship import CareRelationship
from app.models.care_unit import CareUnit
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.models.membership import ActorTenantMembership
from app.models.outbox import OutboxEvent
from app.models.policy import PolicyRegistry
from app.models.service_record import ServiceRecord
from app.models.summary import DailySummary
from app.models.tenant import Tenant

# ─── Fixed time ──────────────────────────────────────────────────────────────
# Schedule preview integration tests use the same disposable DB fixtures below.
#
# Unlike test_repositories.py (which calls repository methods directly with an
# explicit `current_time` argument), these tests exercise the real HTTP
# endpoints, which always evaluate authorization against the actual wall-clock
# time (`datetime.now(UTC)` in app/api/elders.py and app/api/identity.py) —
# by design, a client can never inject its own "current time" into an
# authorization decision. So the bounded CareAssignment window below must
# straddle real "now", not a fixed historical date, or it silently expires as
# real time moves on. Open-ended CareRelationships (effective_to=None) aren't
# affected since they have no upper bound to outlive.
NOW = datetime.now(UTC)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "zone,clock",
    [
        ("UTC", "2026-09-09T10:00:00+00:00"),
        ("Asia/Taipei", "2026-09-08T16:00:00+00:00"),
        ("America/New_York", "2026-03-08T06:30:00+00:00"),
        ("America/New_York", "2026-11-01T05:30:00+00:00"),
    ],
)
async def test_home_care_schedule_preview_is_not_elder_authorization(
    test_engine, seed_api_data, committed_session, monkeypatch, zone, clock
):
    from app.api import elders, identity
    from app.services import authorization_service

    ids = seed_api_data
    fixed = datetime.fromisoformat(clock)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(identity, "datetime", Clock)
    monkeypatch.setattr(elders, "datetime", Clock)
    monkeypatch.setattr(authorization_service, "datetime", Clock)
    elder = await committed_session.get(Elder, ids["elder_2_id"])
    elder.timezone = zone
    memberships = (await committed_session.execute(select(ActorTenantMembership))).scalars().all()
    for membership in memberships:
        membership.effective_from = fixed - timedelta(days=1)
    existing = (await committed_session.execute(select(CareAssignment))).scalars().all()
    for item in existing:
        item.status = "CANCELLED"
    await committed_session.commit()

    def row(start, end, status="CONFIRMED", **overrides):
        fields = dict(
            tenant_id=ids["tenant_id"],
            care_unit_id=ids["care_unit_id"],
            elder_id=ids["elder_2_id"],
            worker_id=ids["worker_id"],
            service_start=start,
            service_end=end,
            status=status,
            service_scope=["assignment:read", "elder:basic:read"],
            version=1,
        )
        fields.update(overrides)
        return CareAssignment(**fields)

    future = row(fixed + timedelta(hours=1), fixed + timedelta(hours=2))
    later = row(fixed + timedelta(hours=3), fixed + timedelta(hours=4))
    committed_session.add_all(
        [
            future,
            later,
            row(fixed + timedelta(days=1), fixed + timedelta(days=1, hours=1)),
            row(fixed - timedelta(hours=1), fixed),
            *[
                row(fixed, fixed + timedelta(hours=1), state)
                for state in ["DRAFT", "CANCELLED", "EXPIRED", "COMPLETED", "NO_SHOW"]
            ],
            row(fixed, fixed + timedelta(hours=1), service_scope=["assignment:read"]),
            row(fixed, fixed + timedelta(hours=1), worker_id=ids["daycare_worker_id"]),
            row(fixed, fixed + timedelta(hours=1), tenant_id=ids["tenant_b_id"]),
            row(fixed, fixed + timedelta(hours=1), elder_id=ids["elder_3_id"]),
        ]
    )
    await committed_session.commit()
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/api/v1/me/home-care-schedule?limit=1")
        assert first.status_code == 200
        data = first.json()["data"]
        assert [x["assignment_id"] for x in data["items"]] == [str(future.id)]
        assert set(data["items"][0]) == {
            "assignment_id",
            "elder_id",
            "display_name",
            "scheduled_start",
            "scheduled_end",
            "status",
            "timezone",
            "local_date",
        }
        assert data["page"]["has_more"]
        # Preview never unlocks even basic profile, let alone summaries/events.
        assert (await client.get(f'/api/v1/elders/{ids["elder_2_id"]}')).status_code == 404
        second = await client.get(
            "/api/v1/me/home-care-schedule", params={"cursor": data["page"]["next_cursor"]}
        )
        assert [x["assignment_id"] for x in second.json()["data"]["items"]] == [str(later.id)]
        later.status = "CANCELLED"
        future.service_end = fixed
        future.service_start = fixed - timedelta(hours=1)
        await committed_session.commit()
        assert (await client.get("/api/v1/me/home-care-schedule")).json()["data"]["items"] == []
        assert (
            await client.get(
                "/api/v1/me/home-care-schedule", params={"cursor": data["page"]["next_cursor"]}
            )
        ).json()["data"]["items"] == []
        assert (await client.get("/api/v1/me/home-care-schedule?cursor=bad")).status_code == 422
        later.status = "CONFIRMED"
        await committed_session.commit()
        unit = await committed_session.get(CareUnit, ids["care_unit_id"])
        tenant = await committed_session.get(Tenant, ids["tenant_id"])
        worker_membership = next(m for m in memberships if m.actor_id == ids["worker_id"])
        for entity, field, denied in [
            (elder, "status", "INACTIVE"),
            (unit, "status", "INACTIVE"),
            (tenant, "status", "INACTIVE"),
            (worker_membership, "effective_to", fixed),
            (later, "service_scope", ["elder:basic:read"]),
        ]:
            previous = getattr(entity, field)
            setattr(entity, field, denied)
            await committed_session.commit()
            assert (await client.get("/api/v1/me/home-care-schedule")).json()["data"]["items"] == []
            setattr(entity, field, previous)
            await committed_session.commit()
    for role, key in [
        ("FAMILY_MEMBER", "family_member_id"),
        ("DAYCARE_CARE_WORKER", "daycare_worker_id"),
    ]:
        app = _build_client_app(test_engine, ids[key], role, ids["tenant_id"])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # AuthorizationDeniedError hides resource existence through the HTTP mapper.
            response = await client.get("/api/v1/me/home-care-schedule")
            assert response.status_code == 404
            assert response.json()["error"]["reason_code"] == "RESOURCE_NOT_FOUND_OR_FORBIDDEN"


# ─── Helper: build client with custom ActorContext ───────────────────────────


@pytest.mark.asyncio
async def test_legacy_service_record_is_not_promoted_or_overwritten(
    test_engine, seed_api_data, committed_session
):
    ids = seed_api_data
    assignment = (
        (
            await committed_session.execute(
                select(CareAssignment).where(
                    CareAssignment.elder_id == ids["elder_2_id"],
                    CareAssignment.status == "CONFIRMED",
                )
            )
        )
        .scalars()
        .first()
    )
    assignment.status = "IN_PROGRESS"
    assignment.service_scope = ["assignment:read", "service_record:read", "service_record:write"]
    legacy = ServiceRecord(
        assignment_id=assignment.id,
        elder_id=assignment.elder_id,
        worker_id=assignment.worker_id,
        service_date=assignment.service_start.date(),
        record_type="SERVICE_NOTE",
        content={"legacy": "Synthetic old note"},
    )
    committed_session.add(legacy)
    await committed_session.commit()
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    path = f"/api/v1/home-care/assignments/{assignment.id}/service-record"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(path)).status_code == 404
        response = await client.post(
            path,
            json={"expected_assignment_version": assignment.version, "content": "New note"},
            headers={"Idempotency-Key": "new-note"},
        )
        assert response.status_code == 409
    await committed_session.refresh(legacy)
    assert legacy.version is None and legacy.status == "DRAFT"
    assert legacy.content == {"legacy": "Synthetic old note"}
    assert await committed_session.scalar(select(func.count()).select_from(ServiceRecord)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrent", [False, True])
async def test_service_record_transaction_and_live_replay(
    test_engine, seed_api_data, committed_session, monkeypatch, concurrent
):
    from app.services import service_record_service

    ids = seed_api_data
    now = datetime.now(UTC)
    assignment = (
        (
            await committed_session.execute(
                select(CareAssignment).where(
                    CareAssignment.elder_id == ids["elder_2_id"],
                    CareAssignment.status == "CONFIRMED",
                )
            )
        )
        .scalars()
        .first()
    )
    assignment.status = "IN_PROGRESS"
    assignment.service_start = now - timedelta(minutes=10)
    assignment.service_end = now + timedelta(hours=1)
    assignment.service_scope = ["assignment:read", "service_record:read", "service_record:write"]
    elder = await committed_session.get(Elder, ids["elder_2_id"])
    elder.timezone = "Asia/Taipei"
    await committed_session.commit()
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    path = f"/api/v1/home-care/assignments/{assignment.id}/service-record"
    body = {"expected_assignment_version": assignment.version, "content": "Synthetic service note"}
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get(path)).status_code == 404
        assert (
            await client.post(
                path,
                json={**body, "expected_assignment_version": 999},
                headers={"Idempotency-Key": "stale"},
            )
        ).status_code == 409
        # Outbox failure must roll back both the formal row and the idempotency claim.
        original = service_record_service.write_outbox_entry

        async def failed_outbox(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError("synthetic transaction failure")

        monkeypatch.setattr(service_record_service, "write_outbox_entry", failed_outbox)
        assert (
            await client.post(path, json=body, headers={"Idempotency-Key": "record"})
        ).status_code == 500
        assert await committed_session.scalar(select(func.count()).select_from(ServiceRecord)) == 0
        assert (
            await committed_session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "care.service_record.completed.v1")
            )
            == 0
        )
        monkeypatch.setattr(service_record_service, "write_outbox_entry", original)
        if concurrent:
            responses = await asyncio.gather(
                *[
                    client.post(path, json=body, headers={"Idempotency-Key": key})
                    for key in ["record", "other"]
                ]
            )
            assert sorted(r.status_code for r in responses) == [201, 409]
            winner = next(r for r in responses if r.status_code == 201)
            key = "record" if responses[0].status_code == 201 else "other"
        else:
            winner = await client.post(path, json=body, headers={"Idempotency-Key": "record"})
            key = "record"
            assert winner.status_code == 201
        data = winner.json()["data"]
        assert (
            data["content"] == body["content"] and data["assignment_version"] == assignment.version
        )
        from zoneinfo import ZoneInfo

        assert (
            data["service_date"]
            == assignment.service_start.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat()
        )
        replay = await client.post(path, json=body, headers={"Idempotency-Key": key})
        assert replay.status_code == 201 and replay.json()["data"] == data
        assert (await client.get(path)).json()["data"] == data
        assert (
            await client.post(
                path, json={**body, "content": "Different"}, headers={"Idempotency-Key": key}
            )
        ).status_code == 409
        assert (
            await client.post(path, json=body, headers={"Idempotency-Key": "duplicate"})
        ).status_code == 409
        assert await committed_session.scalar(select(func.count()).select_from(ServiceRecord)) == 1
        events = (
            (
                await committed_session.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.event_type == "care.service_record.completed.v1"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert set(events[0].payload) == {"service_record_id", "assignment_id", "version", "status"}
        # SQL protection complements the absence of update/delete API commands.
        for statement in [
            'UPDATE eldercare_ai.service_record SET content = \'{"note":"changed"}\'::jsonb',
            "DELETE FROM eldercare_ai.service_record",
        ]:
            with pytest.raises(DBAPIError):
                async with committed_session.begin_nested():
                    await committed_session.execute(text(statement))
        # No content or successful snapshot remains readable after resource/scope revocation.
        member = (
            (
                await committed_session.execute(
                    select(ActorTenantMembership).where(
                        ActorTenantMembership.actor_id == ids["worker_id"]
                    )
                )
            )
            .scalars()
            .one()
        )
        for entity, field, denied in [
            (elder, "status", "INACTIVE"),
            (member, "effective_to", datetime.now(UTC)),
            (assignment, "service_scope", ["assignment:read"]),
            (assignment, "status", "COMPLETED"),
            (assignment, "status", "CANCELLED"),
            (assignment, "service_end", datetime.now(UTC)),
        ]:
            previous = getattr(entity, field)
            setattr(entity, field, denied)
            await committed_session.commit()
            assert (await client.get(path)).status_code == 404
            assert (
                await client.post(path, json=body, headers={"Idempotency-Key": key})
            ).status_code == 404
            setattr(entity, field, previous)
            await committed_session.commit()

    # A different worker or tenant cannot borrow this assignment for writes or reads.
    for actor_id, role, tenant_id in [
        (ids["daycare_worker_id"], "DAYCARE_CARE_WORKER", ids["tenant_id"]),
        (ids["daycare_worker_id"], "HOME_CARE_WORKER", ids["tenant_id"]),
        (ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_b_id"]),
    ]:
        denied_app = _build_client_app(test_engine, actor_id, role, tenant_id)
        async with AsyncClient(
            transport=ASGITransport(app=denied_app), base_url="http://test"
        ) as client:
            assert (await client.get(path)).status_code == 404
            assert (
                await client.post(path, json=body, headers={"Idempotency-Key": key})
            ).status_code == 404


async def _prepare_record_completion(committed_session, ids):
    assignment = await committed_session.scalar(
        select(CareAssignment).where(
            CareAssignment.elder_id == ids["elder_2_id"],
            CareAssignment.status == "CONFIRMED",
        )
    )
    now = datetime.now(UTC)
    assignment.status = "IN_PROGRESS"
    assignment.service_start = now - timedelta(minutes=10)
    assignment.service_end = now + timedelta(hours=1)
    assignment.service_scope = [
        "assignment:read",
        "assignment:complete",
        "service_record:read",
        "service_record:write",
    ]
    await committed_session.commit()
    return assignment


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["record_outbox", "assignment_outbox", "receipt"])
async def test_record_completion_rolls_back_entire_transaction(
    test_engine, seed_api_data, committed_session, monkeypatch, failure
):
    from app.models.idempotency import IdempotencyRecord
    from app.repositories.idempotency_repo import IdempotencyRepository
    from app.services import assignment_service, service_record_service

    ids = seed_api_data
    assignment = await _prepare_record_completion(committed_session, ids)
    version = assignment.version
    path = f"/api/v1/home-care/assignments/{assignment.id}/service-record/complete"
    body = {"expected_assignment_version": version, "content": "Synthetic combined visit note"}
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        target, attr = {
            "record_outbox": (service_record_service, "write_outbox_entry"),
            "assignment_outbox": (assignment_service, "write_outbox_entry"),
            "receipt": (IdempotencyRepository, "complete"),
        }[failure]
        original = getattr(target, attr)

        async def fail_after_write(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError("Synthetic rollback probe")

        with monkeypatch.context() as patch:
            patch.setattr(target, attr, fail_after_write)
            assert (
                await client.post(path, json=body, headers={"Idempotency-Key": "combined"})
            ).status_code == 500
        await committed_session.refresh(assignment)
        assert assignment.status == "IN_PROGRESS" and assignment.version == version
        assert await committed_session.scalar(select(func.count()).select_from(ServiceRecord)) == 0
        assert await committed_session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
        assert (
            await committed_session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0
        )
        await committed_session.commit()
        response = await client.post(path, json=body, headers={"Idempotency-Key": "combined"})
        assert response.status_code == 201
        receipt = response.json()["data"]
        assert set(receipt) == {
            "service_record_id",
            "assignment_id",
            "assignment_version",
            "status",
        }
        assert receipt["assignment_version"] == version + 1
        await committed_session.refresh(assignment)
        assert assignment.status == "COMPLETED" and assignment.version == version + 1
        note = await committed_session.scalar(select(ServiceRecord))
        assert note.assignment_version == version and note.content["note"] == body["content"]
        events = (await committed_session.execute(select(OutboxEvent))).scalars().all()
        assert {event.event_type for event in events} == {
            "care.service_record.completed.v1",
            "care.assignment.completed.v1",
        }
        assert len(events) == 2
        assert all("content" not in event.payload for event in events)
        claim = await committed_session.scalar(select(IdempotencyRecord))
        assert claim.response_body == receipt and claim.status == "COMPLETED"
        await committed_session.commit()
        # Completion revokes record access, even when the caller kept the old key.
        assert (await client.get(path.removesuffix("/complete"))).status_code == 404
        assert (
            await client.post(path, json=body, headers={"Idempotency-Key": "combined"})
        ).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("competitor", ["same_key", "other_key", "separate_complete"])
async def test_record_completion_serializes_concurrent_visit_commands(
    test_engine, seed_api_data, committed_session, competitor
):
    ids = seed_api_data
    assignment = await _prepare_record_completion(committed_session, ids)
    version = assignment.version
    root = f"/api/v1/home-care/assignments/{assignment.id}"
    path = root + "/service-record/complete"
    body = {"expected_assignment_version": version, "content": "Synthetic concurrent note"}
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        other_path = root + "/complete" if competitor == "separate_complete" else path
        other_body = (
            {"expected_version": version, "reason_code": "WORKER_COMPLETED_VISIT"}
            if competitor == "separate_complete"
            else body
        )
        responses = await asyncio.wait_for(
            asyncio.gather(
                client.post(path, json=body, headers={"Idempotency-Key": "combined"}),
                client.post(
                    other_path,
                    json=other_body,
                    headers={
                        "Idempotency-Key": "combined" if competitor == "same_key" else "other"
                    },
                ),
            ),
            timeout=15,
        )
        assert sum(r.status_code in {200, 201} for r in responses) == 1
        assert sum(r.status_code == 404 for r in responses) == 1
        await committed_session.refresh(assignment)
        assert assignment.status == "COMPLETED" and assignment.version == version + 1
        record_count = await committed_session.scalar(
            select(func.count()).select_from(ServiceRecord)
        )
        assert record_count == (
            1 if responses[0].status_code == 201 or responses[1].status_code == 201 else 0
        )
        assert (
            await committed_session.scalar(select(func.count()).select_from(OutboxEvent))
            == 1 + record_count
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_scope", ["assignment:read", "service_record:write", "assignment:complete"]
)
async def test_record_completion_cannot_borrow_scope_from_another_visit(
    test_engine, seed_api_data, committed_session, missing_scope
):
    ids = seed_api_data
    assignment = await _prepare_record_completion(committed_session, ids)
    all_scopes = list(assignment.service_scope)
    assignment.service_scope = [scope for scope in all_scopes if scope != missing_scope]
    committed_session.add(
        CareAssignment(
            tenant_id=assignment.tenant_id,
            care_unit_id=assignment.care_unit_id,
            elder_id=assignment.elder_id,
            worker_id=assignment.worker_id,
            service_start=assignment.service_start,
            service_end=assignment.service_end,
            status="IN_PROGRESS",
            service_scope=all_scopes,
            version=1,
        )
    )
    await committed_session.commit()
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/home-care/assignments/{assignment.id}/service-record/complete",
            json={
                "expected_assignment_version": assignment.version,
                "content": "Synthetic scope probe",
            },
            headers={"Idempotency-Key": "scope-probe"},
        )
        assert response.status_code == 404
    assert await committed_session.scalar(select(func.count()).select_from(ServiceRecord)) == 0
    assert await committed_session.scalar(select(func.count()).select_from(OutboxEvent)) == 0


def _build_client_app(test_engine, actor_id: uuid.UUID, actor_role: str, tenant_id: uuid.UUID):
    """Build a FastAPI app with dependency overrides for a given actor context."""
    app = create_app()
    fake_auth = FakeAuthenticator(
        actor_id=actor_id,
        actor_role=actor_role,
        tenant_id=tenant_id,
    )
    test_db_engine = _TestDatabaseEngine(test_engine)
    app.dependency_overrides[get_authenticator] = lambda: fake_auth
    app.dependency_overrides[get_db_engine] = lambda: test_db_engine
    return app


class _TestDatabaseEngine:
    """Minimal wrapper around a test engine to satisfy DatabaseEngine interface."""

    def __init__(self, engine):
        self._engine = engine
        self._session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    @property
    def engine(self):
        return self._engine

    @property
    def session_factory(self):
        return self._session_factory

    @property
    def is_ready(self) -> bool:
        return True

    async def check_connectivity(self) -> bool:
        return True


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def api_ids():
    """Fixed UUIDs used across all API integration tests."""
    return {
        "tenant_id": uuid.UUID("10000000-0000-4000-a000-000000000001"),
        "tenant_b_id": uuid.UUID("10000000-0000-4000-a000-000000000002"),
        "worker_id": uuid.UUID("20000000-0000-4000-a000-000000000001"),
        "daycare_worker_id": uuid.UUID("20000000-0000-4000-a000-000000000002"),
        "family_member_id": uuid.UUID("20000000-0000-4000-a000-000000000003"),
        "role_mismatch_id": uuid.UUID("20000000-0000-4000-a000-000000000004"),
        "elder_1_id": uuid.UUID("30000000-0000-4000-a000-000000000001"),
        "elder_2_id": uuid.UUID("30000000-0000-4000-a000-000000000002"),
        "elder_3_id": uuid.UUID("30000000-0000-4000-a000-000000000003"),
        "care_unit_id": uuid.UUID("40000000-0000-4000-a000-000000000001"),
    }


@pytest_asyncio.fixture(loop_scope="function")
async def seed_api_data(committed_session, api_ids):
    """Seed the database with data for API integration tests.

    Uses committed_session so data is visible across connections.
    """
    ids = api_ids

    # None of the models below declare an ORM `relationship()` (see
    # app/models/*.py — they use plain `mapped_column(..., ForeignKey(...))`),
    # so SQLAlchemy's unit-of-work cannot infer flush order from FK columns
    # alone. With real foreign keys now enforced by the baseline schema, rows
    # must be flushed in dependency order explicitly: Tenant/Actor first,
    # then CareUnit/Elder (depend on Tenant), then memberships/relationships/
    # assignments (depend on all of the above).

    # Tenants
    tenant = Tenant(id=ids["tenant_id"], name="Test Tenant", tenant_type="CARE_ORGANIZATION")
    tenant_b = Tenant(id=ids["tenant_b_id"], name="Tenant B", tenant_type="HOME_CARE_PROVIDER")
    committed_session.add_all([tenant, tenant_b])

    # Actors
    worker = Actor(id=ids["worker_id"], actor_type="HOME_CARE_WORKER", display_name="Worker One")
    daycare_worker = Actor(
        id=ids["daycare_worker_id"], actor_type="DAYCARE_CARE_WORKER", display_name="DC Worker"
    )
    family_member = Actor(
        id=ids["family_member_id"], actor_type="FAMILY_MEMBER", display_name="Family One"
    )
    role_mismatch_actor = Actor(
        id=ids["role_mismatch_id"],
        actor_type="DAYCARE_CARE_WORKER",
        display_name="Mismatched Worker",
    )
    committed_session.add_all([worker, daycare_worker, family_member, role_mismatch_actor])
    await committed_session.flush()

    # Care Unit (depends on Tenant)
    care_unit = CareUnit(
        id=ids["care_unit_id"],
        tenant_id=ids["tenant_id"],
        unit_type="DAYCARE_CENTER",
        name="Main Unit",
    )
    committed_session.add(care_unit)
    await committed_session.flush()

    # Elders (depend on Tenant)
    elder_1 = Elder(
        id=ids["elder_1_id"],
        tenant_id=ids["tenant_id"],
        display_name="Elder Alice",
        primary_care_setting="DAYCARE",
    )
    elder_2 = Elder(
        id=ids["elder_2_id"],
        tenant_id=ids["tenant_id"],
        display_name="Elder Bob",
        primary_care_setting="DAYCARE",
    )
    # Elder in tenant B — for cross-tenant tests
    elder_3 = Elder(
        id=ids["elder_3_id"],
        tenant_id=ids["tenant_b_id"],
        display_name="Elder Charlie",
        primary_care_setting="HOME_CARE",
    )
    committed_session.add_all([elder_1, elder_2, elder_3])
    await committed_session.flush()

    # actor_tenant_membership rows (TenantMembership + CareUnitMembership merged
    # into ActorTenantMembership — see app/models/membership.py). A row with
    # care_unit_id set counts as BOTH a tenant membership (TenantMembershipRepository
    # doesn't filter on care_unit_id) AND a care-unit membership, so the daycare
    # worker only needs one row to satisfy both old memberships.
    tm_daycare = ActorTenantMembership(
        actor_id=ids["daycare_worker_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=ids["care_unit_id"],
        role_code="DAYCARE_CARE_WORKER",
    )
    tm_worker = ActorTenantMembership(
        actor_id=ids["worker_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=None,
        role_code="HOME_CARE_WORKER",
    )
    tm_family = ActorTenantMembership(
        actor_id=ids["family_member_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=None,
        role_code="FAMILY_MEMBER",
    )
    tm_role_mismatch = ActorTenantMembership(
        actor_id=ids["role_mismatch_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=None,
        role_code="FAMILY_MEMBER",
    )
    committed_session.add_all([tm_daycare, tm_worker, tm_family, tm_role_mismatch])
    await committed_session.flush()

    # CareRelationships
    # 1) DAYCARE_ASSIGNMENT for daycare_worker -> elder_1
    cr_daycare = CareRelationship(
        elder_id=ids["elder_1_id"],
        actor_id=ids["daycare_worker_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=ids["care_unit_id"],
        relationship_type="DAYCARE_ASSIGNMENT",
        scope=["elder:basic:read", "elder:access_context:read"],
        status="ACTIVE",
        effective_from=NOW - timedelta(days=30),
        effective_to=None,
    )
    # 2) FAMILY_SHARE for family_member -> elder_1
    cr_family = CareRelationship(
        elder_id=ids["elder_1_id"],
        actor_id=ids["family_member_id"],
        tenant_id=ids["tenant_id"],
        care_unit_id=None,
        relationship_type="FAMILY_SHARE",
        scope=["elder:basic:read", "elder:access_context:read"],
        status="ACTIVE",
        effective_from=NOW - timedelta(days=60),
        effective_to=None,
    )
    committed_session.add_all([cr_daycare, cr_family])
    await committed_session.flush()

    # CareAssignment for worker -> elder_2
    ca_active = CareAssignment(
        care_unit_id=ids["care_unit_id"],
        elder_id=ids["elder_2_id"],
        worker_id=ids["worker_id"],
        tenant_id=ids["tenant_id"],
        service_start=NOW - timedelta(hours=2),
        service_end=NOW + timedelta(hours=6),
        service_scope=["elder:basic:read", "elder:access_context:read"],
        status="CONFIRMED",
    )
    committed_session.add(ca_active)

    await committed_session.commit()

    yield ids


# ─── Test: GET /api/v1/me ────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,actor_key,elder_key,mode",
    [
        ("DAYCARE_CARE_WORKER", "daycare_worker_id", "elder_1_id", "daycare"),
        ("HOME_CARE_WORKER", "worker_id", "elder_2_id", "home-care"),
        ("FAMILY_MEMBER", "family_member_id", "elder_1_id", "family"),
    ],
)
async def test_dashboard_counts_require_live_professional_scope(
    test_engine, seed_api_data, committed_session, role, actor_key, elder_key, mode
):
    ids = seed_api_data
    if mode == "home-care":
        grant = (
            await committed_session.execute(
                select(CareAssignment).where(CareAssignment.worker_id == ids[actor_key])
            )
        ).scalar_one()
    else:
        grant = (
            await committed_session.execute(
                select(CareRelationship).where(CareRelationship.actor_id == ids[actor_key])
            )
        ).scalar_one()
    app = _build_client_app(test_engine, ids[actor_key], role, ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/v1/me/authorized-elders?mode={mode}&limit=1"
        initial = await client.get(path)
        assert initial.status_code == 200
        assert initial.json()["data"]["items"][0]["open_care_action_count"] is None
        if mode == "home-care":
            grant.service_scope = [*grant.service_scope, "care_action:read"]
        else:
            grant.scope = [*grant.scope, "care_action:read"]
        await committed_session.commit()
        empty = (await client.get(path)).json()["data"]["items"][0]
        assert empty["open_care_action_count"] == (None if mode == "family" else 0)
        # More than a list page: the count must not be capped at 50/100.
        for state in ["OPEN"] * 103 + ["IN_PROGRESS", "POSTPONED", "COMPLETED", "CANCELLED"]:
            committed_session.add(
                CareAction(
                    tenant_id=ids["tenant_id"],
                    elder_id=ids[elder_key],
                    action_type="FOLLOW_UP",
                    title="Synthetic task",
                    assignee_actor_id=ids["worker_id"],
                    created_by_actor_id=ids["worker_id"],
                    due_at=NOW + timedelta(days=1),
                    status=state,
                    resolution="Synthetic outcome" if state != "OPEN" else None,
                )
            )
        # Existing but unauthorized elders and another tenant cannot inflate counts.
        for target, tenant in [
            ("elder_2_id" if elder_key == "elder_1_id" else "elder_1_id", "tenant_id"),
            ("elder_3_id", "tenant_b_id"),
        ]:
            committed_session.add(
                CareAction(
                    tenant_id=ids[tenant],
                    elder_id=ids[target],
                    action_type="FOLLOW_UP",
                    title="Synthetic hidden task",
                    assignee_actor_id=ids["worker_id"],
                    created_by_actor_id=ids["worker_id"],
                    status="OPEN",
                )
            )
        await committed_session.commit()
        response = await client.get(path)
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 1 and not data["page"]["has_more"]
        assert data["items"][0]["open_care_action_count"] == (None if mode == "family" else 105)
        assert "total" not in data
        if mode == "home-care":
            grant.service_end = datetime.now(UTC) - timedelta(seconds=1)
        else:
            grant.effective_to = datetime.now(UTC) - timedelta(seconds=1)
        await committed_session.commit()
        expired = await client.get(path)
        assert expired.status_code == 200 and expired.json()["data"]["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,actor_key,elder_key,mode",
    [
        ("DAYCARE_CARE_WORKER", "daycare_worker_id", "elder_1_id", "daycare"),
        ("HOME_CARE_WORKER", "worker_id", "elder_2_id", "home-care"),
        ("FAMILY_MEMBER", "family_member_id", "elder_1_id", "family"),
    ],
)
async def test_pending_event_counts_require_both_live_scopes(
    test_engine, seed_api_data, committed_session, role, actor_key, elder_key, mode
):
    ids = seed_api_data
    model = CareAssignment if mode == "home-care" else CareRelationship
    owner = model.worker_id if mode == "home-care" else model.actor_id
    grant = (
        await committed_session.execute(select(model).where(owner == ids[actor_key]))
    ).scalar_one()
    scope_attr = "service_scope" if mode == "home-care" else "scope"
    base_scopes = list(getattr(grant, scope_attr))
    app = _build_client_app(test_engine, ids[actor_key], role, ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/v1/me/authorized-elders?mode={mode}&limit=1"
        # Read-only, review-only, and neither cannot reveal pending metadata.
        for scopes in [[], ["care_event:read"], ["care_event:review"]]:
            setattr(grant, scope_attr, base_scopes + scopes)
            await committed_session.commit()
            response = await client.get(path)
            assert response.status_code == 200
            assert response.json()["data"]["items"][0]["pending_event_review_count"] is None
        setattr(grant, scope_attr, base_scopes + ["care_event:read", "care_event:review"])
        await committed_session.commit()
        assert (await client.get(path)).json()["data"]["items"][0][
            "pending_event_review_count"
        ] == (None if mode == "family" else 0)
        for state in (
            ["NEEDS_REVIEW"] * 103
            + ["CANDIDATE"] * 2
            + ["VERIFIED", "CORRECTED", "REJECTED", "EXCLUDED", "DELETED"]
        ):
            committed_session.add(
                CareEvent(
                    tenant_id=ids["tenant_id"],
                    elder_id=ids[elder_key],
                    event_type="MEAL",
                    status=state,
                    consent_version=1,
                )
            )
        for target, tenant in [
            ("elder_2_id" if elder_key == "elder_1_id" else "elder_1_id", "tenant_id"),
            ("elder_3_id", "tenant_b_id"),
        ]:
            committed_session.add(
                CareEvent(
                    tenant_id=ids[tenant],
                    elder_id=ids[target],
                    event_type="MEAL",
                    status="NEEDS_REVIEW",
                    consent_version=1,
                )
            )
        await committed_session.commit()
        response = await client.get(path)
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["pending_event_review_count"] == (None if mode == "family" else 105)
        assert "total" not in data
        setattr(
            grant,
            "service_end" if mode == "home-care" else "effective_to",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        await committed_session.commit()
        assert (await client.get(path)).json()["data"]["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,actor_key,elder_key,mode,zone,start,as_of",
    [
        (
            "DAYCARE_CARE_WORKER",
            "daycare_worker_id",
            "elder_1_id",
            "daycare",
            "Asia/Taipei",
            "2026-09-08T16:00:00+00:00",
            "2026-09-08T16:02:00+00:00",
        ),
        (
            "HOME_CARE_WORKER",
            "worker_id",
            "elder_2_id",
            "home-care",
            "America/New_York",
            "2026-03-08T05:00:00+00:00",
            "2026-03-09T03:59:00+00:00",
        ),
        (
            "DAYCARE_CARE_WORKER",
            "daycare_worker_id",
            "elder_1_id",
            "daycare",
            "America/New_York",
            "2026-11-01T04:00:00+00:00",
            "2026-11-02T04:59:00+00:00",
        ),
        (
            "FAMILY_MEMBER",
            "family_member_id",
            "elder_1_id",
            "family",
            "Asia/Taipei",
            "2026-09-08T16:00:00+00:00",
            "2026-09-08T16:02:00+00:00",
        ),
    ],
)
async def test_interaction_metrics_scope_calendar_and_session_dedup(
    test_engine,
    seed_api_data,
    committed_session,
    monkeypatch,
    role,
    actor_key,
    elder_key,
    mode,
    zone,
    start,
    as_of,
):
    from zoneinfo import ZoneInfo

    from app.api import identity

    ids = seed_api_data
    start, as_of = datetime.fromisoformat(start), datetime.fromisoformat(as_of)

    # Only the metric snapshot clock is fixed. Live authorization keeps real time.
    # Identity list also needs the real clock for time-bounded home-care grants.
    original_metrics = identity.get_interaction_metrics

    async def snapshot_metrics(session, actor, elders, _now):
        return await original_metrics(session, actor, elders, as_of)

    monkeypatch.setattr(identity, "get_interaction_metrics", snapshot_metrics)
    model = CareAssignment if mode == "home-care" else CareRelationship
    owner = model.worker_id if mode == "home-care" else model.actor_id
    grant = (
        await committed_session.execute(select(model).where(owner == ids[actor_key]))
    ).scalar_one()
    scope_attr = "service_scope" if mode == "home-care" else "scope"
    base = list(getattr(grant, scope_attr))
    elder = await committed_session.get(Elder, ids[elder_key])
    elder.timezone = zone
    await committed_session.commit()
    app = _build_client_app(test_engine, ids[actor_key], role, ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/v1/me/authorized-elders?mode={mode}&limit=1"
        assert (await client.get(path)).json()["data"]["items"][0]["interaction_metrics"] is None
        setattr(grant, scope_attr, base + ["voice_session:read"])
        await committed_session.commit()
        empty = (await client.get(path)).json()["data"]["items"][0]["interaction_metrics"]
        if mode != "family":
            assert empty["today_count"] == 0 and empty["last_interaction_at"] is None
        else:
            assert empty is None

        policy = PolicyRegistry(
            policy_code="synthetic-interactions",
            policy_type="CONSENT",
            version="v1",
            status="ACTIVE",
            policy_payload={},
            effective_from=start - timedelta(days=2),
        )
        committed_session.add(policy)
        await committed_session.flush()
        consent = ConsentGrant(
            elder_id=ids[elder_key],
            purpose_code="BASIC_VOICE",
            status="GRANTED",
            version=1,
            granted_by_actor_id=ids[actor_key],
            policy_id=policy.id,
            effective_at=start - timedelta(days=2),
        )
        committed_session.add(consent)
        await committed_session.flush()

        async def add_session(
            ended,
            states=("SUCCESS",),
            state="COMPLETED",
            target=None,
            tenant=None,
            run_tenant=None,
            run_elder=None,
        ):
            row = ConversationSession(
                id=uuid.uuid4(),
                tenant_id=tenant or ids["tenant_id"],
                elder_id=target or ids[elder_key],
                initiator_type="ELDER",
                language_route="ZH_TW",
                input_mode="text",
                state=state,
                started_at=ended - timedelta(minutes=1),
                ended_at=ended,
                trace_id=str(uuid.uuid4()),
                consent_id=consent.id,
                consent_version=1,
            )
            committed_session.add(row)
            await committed_session.flush()
            for result in states:
                committed_session.add(
                    AgentRun(
                        session_id=row.id,
                        tenant_id=run_tenant or row.tenant_id,
                        elder_id=run_elder or row.elder_id,
                        agent_id="synthetic-companion",
                        agent_version="v1",
                        result_status=result,
                        started_at=row.started_at,
                        completed_at=ended,
                        trace_id=str(uuid.uuid4()),
                    )
                )

        await add_session(start - timedelta(microseconds=1))
        await committed_session.commit()
        historical = (await client.get(path)).json()["data"]["items"][0]["interaction_metrics"]
        if mode != "family":
            assert historical["today_count"] == 0
            assert datetime.fromisoformat(historical["last_interaction_at"]) == start - timedelta(
                microseconds=1
            )
        for _ in range(103):
            await add_session(start, states=("SUCCESS", "SUCCESS"))
        await add_session(as_of, states=("BLOCKED",))
        await add_session(as_of, states=("HUMAN_REVIEW",))
        await add_session(as_of + timedelta(seconds=1))  # future
        await add_session(as_of, states=("DEPENDENCY_FAILED",))
        await add_session(as_of, states=())  # manual completion without a response
        for state in ["CREATED", "PROCESSING", "FAILED", "CANCELLED"]:
            await add_session(as_of, state=state)
        other = ids["elder_2_id" if elder_key == "elder_1_id" else "elder_1_id"]
        await add_session(as_of, target=other)
        await add_session(as_of, target=ids["elder_3_id"], tenant=ids["tenant_b_id"])
        await add_session(as_of, run_tenant=ids["tenant_b_id"])
        await add_session(as_of, run_elder=other)
        await committed_session.commit()
        for _ in range(2):  # reading again never changes the count
            response = await client.get(path)
            assert response.status_code == 200
            items = response.json()["data"]["items"]
            assert len(items) == 1
            metric = items[0]["interaction_metrics"]
            if mode == "family":
                assert metric is None
            else:
                assert metric["today_count"] == 105
                assert datetime.fromisoformat(metric["last_interaction_at"]) == as_of
                assert metric["local_date"] == as_of.astimezone(ZoneInfo(zone)).date().isoformat()
                assert metric["timezone"] == zone
        setattr(grant, scope_attr, base)
        await committed_session.commit()
        assert (await client.get(path)).json()["data"]["items"][0]["interaction_metrics"] is None
        setattr(
            grant,
            "service_end" if mode == "home-care" else "effective_to",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        await committed_session.commit()
        assert (await client.get(path)).json()["data"]["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,actor_key,elder_key,mode,zone,clock",
    [
        (
            "DAYCARE_CARE_WORKER",
            "daycare_worker_id",
            "elder_1_id",
            "daycare",
            "Asia/Taipei",
            "2026-09-08T16:00:00+00:00",
        ),
        (
            "HOME_CARE_WORKER",
            "worker_id",
            "elder_2_id",
            "home-care",
            "America/New_York",
            "2026-03-09T03:59:00+00:00",
        ),
        (
            "DAYCARE_CARE_WORKER",
            "daycare_worker_id",
            "elder_1_id",
            "daycare",
            "America/New_York",
            "2026-11-02T04:59:00+00:00",
        ),
        (
            "FAMILY_MEMBER",
            "family_member_id",
            "elder_1_id",
            "family",
            "Asia/Taipei",
            "2026-09-08T16:00:00+00:00",
        ),
    ],
)
async def test_dashboard_summary_visibility_and_local_day(
    test_engine,
    seed_api_data,
    committed_session,
    monkeypatch,
    role,
    actor_key,
    elder_key,
    mode,
    zone,
    clock,
):
    from zoneinfo import ZoneInfo

    from app.api import identity

    ids = seed_api_data
    as_of = datetime.fromisoformat(clock)
    day = as_of.astimezone(ZoneInfo(zone)).date()
    original = identity.get_daily_summary_snapshots

    async def snapshot(session, actor, elders, _now):
        return await original(session, actor, elders, as_of)

    monkeypatch.setattr(identity, "get_daily_summary_snapshots", snapshot)
    model = CareAssignment if mode == "home-care" else CareRelationship
    owner = model.worker_id if mode == "home-care" else model.actor_id
    grant = (
        await committed_session.execute(select(model).where(owner == ids[actor_key]))
    ).scalar_one()
    scope_attr = "service_scope" if mode == "home-care" else "scope"
    base = list(getattr(grant, scope_attr))
    elder = await committed_session.get(Elder, ids[elder_key])
    elder.timezone = zone
    await committed_session.commit()
    app = _build_client_app(test_engine, ids[actor_key], role, ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/v1/me/authorized-elders?mode={mode}&limit=1"

        async def get_snapshot():
            response = await client.get(path)
            assert response.status_code == 200
            items = response.json()["data"]["items"]
            assert len(items) == 1 and items[0]["elder_id"] == str(ids[elder_key])
            return items[0]["daily_summary"]

        assert await get_snapshot() is None
        setattr(grant, scope_attr, base + ["summary:read"])
        await committed_session.commit()
        empty = await get_snapshot()
        if mode != "family":
            assert empty == {
                "local_date": day.isoformat(),
                "timezone": zone,
                "as_of": as_of.isoformat().replace("+00:00", "Z"),
                "summary": None,
            }
        else:
            assert empty is None

        def row(target, tenant, date_value, kind="PROFESSIONAL_DAILY", status="PUBLISHED"):
            return DailySummary(
                id=uuid.uuid4(),
                tenant_id=tenant,
                elder_id=target,
                summary_date=date_value,
                summary_type=kind,
                status=status,
                current_version=1,
            )

        # None of these may become this elder's current professional daily summary.
        other = ids["elder_2_id" if elder_key == "elder_1_id" else "elder_1_id"]
        committed_session.add_all(
            [
                row(ids[elder_key], ids["tenant_id"], day - timedelta(days=1)),
                row(ids[elder_key], ids["tenant_id"], day + timedelta(days=1)),
                row(ids[elder_key], ids["tenant_id"], day, "FAMILY_DAILY"),
                row(other, ids["tenant_id"], day),
                row(ids["elder_3_id"], ids["tenant_b_id"], day),
            ]
        )
        await committed_session.commit()
        assert await get_snapshot() == empty
        today = row(ids[elder_key], ids["tenant_b_id"], day, status="DRAFT")
        committed_session.add(today)
        await committed_session.commit()
        assert await get_snapshot() == empty  # mismatched summary tenant
        # Tenant identity is immutable. Replace the synthetic mismatched row
        # before creating the valid fixture for the same unique summary key.
        await committed_session.delete(today)
        await committed_session.flush()
        today = row(ids[elder_key], ids["tenant_id"], day, status="DRAFT")
        committed_session.add(today)
        await committed_session.commit()
        assert await get_snapshot() == empty  # hidden draft must equal absence
        for status in ["DRAFT", "NEEDS_REVIEW", "STALE", "WITHDRAWN", "READY", "PUBLISHED"]:
            today.status = status
            await committed_session.commit()
            for review in [False, True]:
                setattr(
                    grant,
                    scope_attr,
                    base + ["summary:read"] + (["summary:review"] if review else []),
                )
                await committed_session.commit()
                actual = await get_snapshot()
                if mode == "family" or (not review and status not in ["READY", "PUBLISHED"]):
                    assert actual == empty
                else:
                    assert actual["summary"] == {
                        "summary_id": str(today.id),
                        "status": status,
                        "version": 1,
                    }
        # Metadata is not a capability: removing read keeps the object unavailable.
        setattr(grant, scope_attr, base + ["summary:review"])
        await committed_session.commit()
        assert await get_snapshot() is None
        setattr(
            grant,
            "service_end" if mode == "home-care" else "effective_to",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        await committed_session.commit()
        assert (await client.get(path)).json()["data"]["items"] == []


class TestGetMe:
    """Tests for GET /api/v1/me endpoint."""

    @pytest.mark.asyncio
    async def test_returns_actor_profile(self, test_engine, seed_api_data):
        """GET /me returns actor profile with care_unit_ids."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["daycare_worker_id"],
            actor_role="DAYCARE_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "meta" in body
        data = body["data"]
        assert data["actor_id"] == str(ids["daycare_worker_id"])
        assert data["actor_type"] == "DAYCARE_CARE_WORKER"
        assert data["display_name"] == "DC Worker"
        assert data["tenant_id"] == str(ids["tenant_id"])
        assert data["role"] == "DAYCARE_CARE_WORKER"
        assert isinstance(data["care_unit_ids"], list)
        assert str(ids["care_unit_id"]) in data["care_unit_ids"]

    @pytest.mark.asyncio
    async def test_rejects_tenant_membership_role_mismatch(self, test_engine, seed_api_data):
        """A global actor type cannot substitute for a different tenant-local role."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["role_mismatch_id"],
            actor_role="DAYCARE_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_worker_returns_empty_care_units(self, test_engine, seed_api_data):
        """GET /me for a worker without care unit memberships returns empty list."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["care_unit_ids"] == []


# ─── Test: GET /api/v1/me/authorized-elders ──────────────────────────────────


class TestGetAuthorizedElders:
    """Tests for GET /api/v1/me/authorized-elders endpoint."""

    @pytest.mark.asyncio
    async def test_family_mode_returns_elders(self, test_engine, seed_api_data):
        """Family mode returns elders the family member is authorized for."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=family")

        assert response.status_code == 200
        body = response.json()
        data = body["data"]
        assert "items" in data
        assert "page" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["elder_id"] == str(ids["elder_1_id"])
        assert data["items"][0]["display_name"] == "Elder Alice"

    @pytest.mark.asyncio
    async def test_home_care_mode_returns_elders(self, test_engine, seed_api_data):
        """Home-care mode returns elders the worker has active assignments for."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["worker_id"],
            actor_role="HOME_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=home-care")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["elder_id"] == str(ids["elder_2_id"])

    @pytest.mark.asyncio
    async def test_daycare_mode_returns_elders(self, test_engine, seed_api_data):
        """Daycare mode returns elders the daycare worker is authorized for."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["daycare_worker_id"],
            actor_role="DAYCARE_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=daycare")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["elder_id"] == str(ids["elder_1_id"])
        assert data["items"][0]["display_name"] == "Elder Alice"

    @pytest.mark.asyncio
    async def test_invalid_mode_returns_422(self, test_engine, seed_api_data):
        """Invalid mode value returns 422 validation error."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["worker_id"],
            actor_role="HOME_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=invalid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_incompatible_role_mode_returns_403(self, test_engine, seed_api_data):
        """Incompatible role/mode pair returns 403."""
        ids = seed_api_data
        # FAMILY_MEMBER trying daycare mode → 403
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=daycare")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_pagination_metadata_present(self, test_engine, seed_api_data):
        """Response includes pagination metadata."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/me/authorized-elders?mode=family&limit=10")

        assert response.status_code == 200
        page = response.json()["data"]["page"]
        assert "has_more" in page
        assert "limit" in page
        assert page["has_more"] is False
        assert page["limit"] == 10


# ─── Test: GET /api/v1/elders/{elder_id} ─────────────────────────────────────


class TestGetElder:
    """Tests for GET /api/v1/elders/{elder_id} endpoint."""

    @pytest.mark.asyncio
    async def test_authorized_access_returns_200(self, test_engine, seed_api_data):
        """Authorized actor gets 200 with elder data."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_1_id']}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["elder_id"] == str(ids["elder_1_id"])
        assert data["display_name"] == "Elder Alice"
        assert data["status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_unauthorized_access_returns_404(self, test_engine, seed_api_data):
        """Unauthorized actor gets 404 (non-disclosure)."""
        ids = seed_api_data
        # family_member has no relationship to elder_2
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_2_id']}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_elder_returns_404(self, test_engine, seed_api_data):
        """Non-existent elder_id returns 404."""
        ids = seed_api_data
        non_existent_id = uuid.UUID("99999999-9999-4999-9999-999999999999")
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{non_existent_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_non_disclosure_responses_identical(self, test_engine, seed_api_data):
        """Unauthorized and non-existent elder responses are structurally identical.

        This validates the non-disclosure pattern: an attacker cannot
        distinguish between 'elder exists but I'm not authorized' and
        'elder does not exist'.
        """
        ids = seed_api_data
        non_existent_id = uuid.UUID("99999999-9999-4999-9999-999999999999")

        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Unauthorized: elder_2 exists but actor lacks access
            resp_unauthorized = await client.get(f"/api/v1/elders/{ids['elder_2_id']}")
            # Non-existent: random UUID
            resp_nonexistent = await client.get(f"/api/v1/elders/{non_existent_id}")

        # Same status code
        assert resp_unauthorized.status_code == 404
        assert resp_nonexistent.status_code == 404

        # Same response body structure and error code
        body_unauth = resp_unauthorized.json()
        body_nonexist = resp_nonexistent.json()

        assert "error" in body_unauth
        assert "error" in body_nonexist
        assert body_unauth["error"]["code"] == body_nonexist["error"]["code"]
        assert body_unauth["error"]["message"] == body_nonexist["error"]["message"]

    @pytest.mark.asyncio
    async def test_home_care_worker_authorized(self, test_engine, seed_api_data):
        """HOME_CARE_WORKER with valid assignment gets 200."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["worker_id"],
            actor_role="HOME_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_2_id']}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["elder_id"] == str(ids["elder_2_id"])
        assert data["display_name"] == "Elder Bob"


# ─── Test: GET /api/v1/elders/{elder_id}/access-context ──────────────────────


class TestGetElderAccessContext:
    """Tests for GET /api/v1/elders/{elder_id}/access-context endpoint."""

    @pytest.mark.asyncio
    async def test_authorized_returns_access_context(self, test_engine, seed_api_data):
        """Authorized actor gets 200 with access context details."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_1_id']}/access-context")

        assert response.status_code == 200
        data = response.json()["data"]
        assert "purpose" in data
        assert "allowed_actions" in data
        assert "source_type" in data
        assert isinstance(data["allowed_actions"], list)
        assert len(data["allowed_actions"]) > 0

    @pytest.mark.asyncio
    async def test_unauthorized_returns_404(self, test_engine, seed_api_data):
        """Unauthorized actor gets 404 for access-context (non-disclosure)."""
        ids = seed_api_data
        # family_member has no relationship to elder_2
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_2_id']}/access-context")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_elder_returns_404(self, test_engine, seed_api_data):
        """Non-existent elder returns 404 for access-context."""
        ids = seed_api_data
        non_existent_id = uuid.UUID("99999999-9999-4999-9999-999999999999")
        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{non_existent_id}/access-context")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_non_disclosure_access_context(self, test_engine, seed_api_data):
        """Access-context: unauthorized vs non-existent responses are identical."""
        ids = seed_api_data
        non_existent_id = uuid.UUID("99999999-9999-4999-9999-999999999999")

        app = _build_client_app(
            test_engine,
            actor_id=ids["family_member_id"],
            actor_role="FAMILY_MEMBER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_unauthorized = await client.get(
                f"/api/v1/elders/{ids['elder_2_id']}/access-context"
            )
            resp_nonexistent = await client.get(f"/api/v1/elders/{non_existent_id}/access-context")

        assert resp_unauthorized.status_code == 404
        assert resp_nonexistent.status_code == 404

        body_unauth = resp_unauthorized.json()
        body_nonexist = resp_nonexistent.json()

        assert body_unauth["error"]["code"] == body_nonexist["error"]["code"]
        assert body_unauth["error"]["message"] == body_nonexist["error"]["message"]

    @pytest.mark.asyncio
    async def test_home_care_worker_access_context(self, test_engine, seed_api_data):
        """HOME_CARE_WORKER with valid assignment gets access-context."""
        ids = seed_api_data
        app = _build_client_app(
            test_engine,
            actor_id=ids["worker_id"],
            actor_role="HOME_CARE_WORKER",
            tenant_id=ids["tenant_id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/elders/{ids['elder_2_id']}/access-context")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["purpose"] == "elder_care_access"
        assert "elder:basic:read" in data["allowed_actions"]
