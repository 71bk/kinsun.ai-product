"""Rollback-only HTTP/SQL cases and a disposable-DB committed concurrency case."""

import asyncio
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, OptimisticConcurrencyError
from app.db.session import get_db_session
from app.main import create_app
from app.middleware.actor_guard import require_active_actor
from app.models.actor import Actor
from app.models.assisted_elder_session import AssistedElderSession
from app.models.care_assignment import CareAssignment
from app.models.care_relationship import CareRelationship
from app.models.care_unit import CareUnit
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.models.elder_enrollment import ElderEnrollment
from app.models.elder_enrollment_change import ElderEnrollmentChange
from app.models.membership import ActorTenantMembership
from app.models.outbox import OutboxEvent
from app.models.policy import PolicyRegistry
from app.models.tenant import Tenant
from app.repositories.care_assignment_repo import CareAssignmentRepository
from app.repositories.care_relationship_repo import CareRelationshipRepository
from app.schemas.assisted_elder import CreateAccountlessElderRequest
from app.schemas.elder_enrollment import EnrollmentCommand
from app.services.assisted_elder_session_service import (
    AssistedElderSessionPolicy,
    AssistedElderSessionService,
)
from app.services.elder_enrollment_service import ElderEnrollmentService
from app.services.elder_onboarding_service import ElderOnboardingService


@pytest.mark.asyncio(loop_scope="function")
async def test_concurrent_enrollment_commands(committed_session):
    """Disposable CI DB only; the fixture owns committed-data cleanup."""
    db = committed_session
    tenant_id, worker_id, unit_id = uuid4(), uuid4(), uuid4()
    db.add_all(
        [
            Tenant(id=tenant_id, name="Synthetic concurrency", tenant_type="CARE_ORGANIZATION"),
            Actor(id=worker_id, actor_type="DAYCARE_CARE_WORKER", display_name="Synthetic"),
        ]
    )
    await db.flush()
    db.add(CareUnit(id=unit_id, tenant_id=tenant_id, unit_type="DAYCARE_CENTER", name="Synthetic"))
    await db.flush()
    for unit in [None, unit_id]:
        db.add(
            ActorTenantMembership(
                actor_id=worker_id,
                tenant_id=tenant_id,
                care_unit_id=unit,
                role_code="DAYCARE_CARE_WORKER",
                status="ACTIVE",
                effective_from=datetime.now(UTC) - timedelta(hours=1),
            )
        )
    await db.flush()
    actor = ActorContext(worker_id, "DAYCARE_CARE_WORKER", tenant_id)
    bundle = await ElderOnboardingService(db, tenant_id).create(
        organization_id=tenant_id,
        actor_context=actor,
        request=CreateAccountlessElderRequest(display_name="Synthetic", care_unit_id=unit_id),
    )
    enrollment_id = bundle.enrollment.id
    await db.commit()

    async def command(action, version, key):
        async with AsyncSession(db.bind, expire_on_commit=False) as writer, writer.begin():
            return await ElderEnrollmentService(writer, actor).command(
                enrollment_id,
                action,
                EnrollmentCommand(expected_version=version, reason="Synthetic"),
                key,
                "synthetic",
            )

    receipts = await asyncio.wait_for(
        asyncio.gather(command("suspend", 1, "same-key"), command("suspend", 1, "same-key")),
        timeout=20,
    )
    assert receipts[0] == receipts[1]
    results = await asyncio.wait_for(
        asyncio.gather(
            command("resume", 2, "first"), command("resume", 2, "second"), return_exceptions=True
        ),
        timeout=20,
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, OptimisticConcurrencyError) for r in results) == 1
    assert (await command("end", 3, "end"))["version"] == 4
    assert (
        await db.scalar(
            select(func.count())
            .select_from(ElderEnrollmentChange)
            .where(ElderEnrollmentChange.enrollment_id == enrollment_id)
        )
        == 3
    )
    assert (
        await db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "elder.enrollment_changed.v1",
            )
        )
        == 3
    )


@pytest.mark.asyncio(loop_scope="function")
async def test_enrollment_http_lifecycle(db_session, monkeypatch):
    db = db_session
    monkeypatch.setattr(get_settings(), "assisted_elder_sessions_enabled", True)
    now = datetime.now(UTC)
    tenant_id, worker_id, unit_id = uuid4(), uuid4(), uuid4()
    db.add_all(
        [
            Tenant(id=tenant_id, name="Synthetic enrollment", tenant_type="CARE_ORGANIZATION"),
            Actor(id=worker_id, actor_type="DAYCARE_CARE_WORKER", display_name="Synthetic manager"),
        ]
    )
    await db.flush()
    db.add(
        CareUnit(id=unit_id, tenant_id=tenant_id, unit_type="DAYCARE_CENTER", name="Synthetic unit")
    )
    await db.flush()
    for care_unit_id in [None, unit_id]:
        db.add(
            ActorTenantMembership(
                actor_id=worker_id,
                tenant_id=tenant_id,
                care_unit_id=care_unit_id,
                role_code="DAYCARE_CARE_WORKER",
                status="ACTIVE",
                effective_from=now - timedelta(hours=1),
            )
        )
    await db.flush()
    actor = ActorContext(worker_id, "DAYCARE_CARE_WORKER", tenant_id)
    app = create_app()

    async def request_session():
        async with db.begin_nested():
            yield db

    app.dependency_overrides[get_db_session] = request_session
    app.dependency_overrides[require_active_actor] = lambda: actor
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def call(method, path, body=None, expected=200, key=None):
            response = await client.request(
                method, path, json=body, headers={"Idempotency-Key": key or str(uuid4())}
            )
            assert response.status_code == expected, f"{method} {path}: {response.status_code}"
            if expected < 300 and "elder-enrollments" in path:
                assert response.headers["cache-control"] == "no-store"
            return response.json()["data"] if expected < 300 else response.json()

        created = await call(
            "POST",
            f"/api/v1/organizations/{tenant_id}/elders",
            {"display_name": "Synthetic elder", "care_unit_id": str(unit_id)},
            201,
            "create",
        )
        elder_id, enrollment_id = UUID(created["elder_id"]), UUID(created["enrollment_id"])
        base = f"/api/v1/elder-enrollments/{enrollment_id}"
        elder_base = f"/api/v1/elders/{elder_id}"
        assert (await call("GET", base))["version"] == 1
        assert (await call("GET", "/api/v1/elder-enrollments"))["items"][0]["can_manage"]
        await call("POST", base + "/resume", {"reason": "Invalid", "expected_version": 1}, 409)
        await call("POST", base + "/suspend", {"reason": " ", "expected_version": 1}, 422)
        await call(
            "POST",
            base + "/suspend",
            {"reason": "Test", "expected_version": 1, "actor_id": str(worker_id)},
            422,
        )

        service = AssistedElderSessionService(
            db, AssistedElderSessionPolicy.from_settings(get_settings()), enabled=True
        )
        issued = await service.issue(actor_context=actor, elder_id=elder_id)
        old_pairing = issued.pairing_token
        activated = await service.exchange(old_pairing)
        old_token = activated.session_token
        old_session_id = activated.assisted_session.id
        # Pending and in-progress visits must never be revived by resume.
        assignment_id = uuid4()
        db.add(
            CareAssignment(
                id=assignment_id,
                tenant_id=tenant_id,
                care_unit_id=unit_id,
                elder_id=elder_id,
                worker_id=worker_id,
                status="CONFIRMED",
                service_start=now - timedelta(minutes=1),
                service_end=now + timedelta(hours=1),
                service_scope=[],
            )
        )
        await db.flush()
        body = {"reason": "Temporary absence", "expected_version": 1}
        # A same-day enrollment must appear in today's schedule immediately.
        assignments = CareAssignmentRepository(db, tenant_id)
        assert (
            len(
                await assignments.list_for_worker(
                    worker_id=worker_id,
                    window_start=now.replace(hour=0, minute=0, second=0, microsecond=0),
                    window_end=now + timedelta(days=1),
                )
            )
            == 1
        )
        policy_id, consent_id, conversation_id = uuid4(), uuid4(), uuid4()
        db.add(
            PolicyRegistry(
                id=policy_id,
                owner_tenant_id=tenant_id,
                policy_code=f"synthetic-{uuid4()}",
                policy_type="CONSENT",
                version="1",
                status="ACTIVE",
                policy_payload={},
            )
        )
        await db.flush()
        db.add(
            ConsentGrant(
                id=consent_id,
                elder_id=elder_id,
                purpose_code="BASIC_VOICE",
                version=1,
                policy_id=policy_id,
                granted_by_actor_id=None,
                confirmation_method="ASSISTED_TABLET_ACKNOWLEDGEMENT",
                recorded_by_actor_id=worker_id,
                assisted_session_id=old_session_id,
            )
        )
        await db.flush()
        db.add(
            ConversationSession(
                id=conversation_id,
                tenant_id=tenant_id,
                elder_id=elder_id,
                initiator_actor_id=worker_id,
                initiator_type="CAREGIVER",
                language_route="ZH_TW",
                trace_id=str(uuid4()),
                consent_id=consent_id,
                consent_version=1,
                assisted_session_id=old_session_id,
            )
        )
        await db.flush()

        # A failed outbox insert rolls back the lifecycle and every dependent revocation.
        async def unavailable(*args, **kwargs):
            raise RuntimeError("Synthetic outbox outage")

        with monkeypatch.context() as patch:
            patch.setattr("app.services.elder_enrollment_service.write_outbox_entry", unavailable)
            with pytest.raises(RuntimeError, match="Synthetic outbox outage"):
                async with db.begin_nested():
                    await ElderEnrollmentService(db, actor).command(
                        enrollment_id,
                        "suspend",
                        EnrollmentCommand(**body),
                        "atomic-rollback",
                        "synthetic",
                    )
        assert (
            await db.scalar(
                select(ElderEnrollment.status).where(ElderEnrollment.id == enrollment_id)
            )
            == "ACTIVE"
        )
        assert (
            await db.scalar(
                select(AssistedElderSession.status).where(AssistedElderSession.id == old_session_id)
            )
            == "ACTIVE"
        )
        assert (
            await db.scalar(select(CareAssignment.status).where(CareAssignment.id == assignment_id))
            == "CONFIRMED"
        )
        assert (
            await db.scalar(
                select(ConversationSession.state).where(ConversationSession.id == conversation_id)
            )
            == "CREATED"
        )
        suspended = await call("POST", base + "/suspend", body, key="suspend")
        assert suspended["status"] == "SUSPENDED" and suspended["version"] == 2
        assert await call("POST", base + "/suspend", body, key="suspend") == suspended
        await call("POST", base + "/suspend", {**body, "reason": "Different"}, 409, "suspend")
        await call("POST", base + "/resume", {"reason": "Return", "expected_version": 1}, 409)
        for suffix in ["", "/profile", "/access-context"]:
            await call("GET", elder_base + suffix, expected=404)
        await call(
            "POST",
            elder_base + "/care-profile",
            {"category": "ALLERGY", "content": "Synthetic", "reason": "New"},
            404,
        )
        await call("POST", elder_base + "/assisted-sessions", {}, 404)
        await call(
            "POST",
            f"/api/v1/organizations/{tenant_id}/elders",
            {"display_name": "Synthetic elder", "care_unit_id": str(unit_id)},
            404,
            "create",
        )
        assert (await call("GET", base))["status"] == "SUSPENDED"
        assert not await CareRelationshipRepository(db, tenant_id).find_authorized_elders_by_actor(
            worker_id, ["DAYCARE_ASSIGNMENT"], datetime.now(UTC)
        )
        assert (
            await db.scalar(
                select(ConversationSession.state).where(ConversationSession.id == conversation_id)
            )
            == "CANCELLED"
        )
        assert (
            await db.scalar(select(ConsentGrant.status).where(ConsentGrant.id == consent_id))
            == "GRANTED"
        )
        assert (
            await db.scalar(
                select(AssistedElderSession.status).where(AssistedElderSession.id == old_session_id)
            )
            == "ENDED"
        )
        assert (
            await db.scalar(select(CareAssignment.status).where(CareAssignment.id == assignment_id))
            == "CANCELLED"
        )
        with pytest.raises(AuthenticationError):
            await service.resolve_current(old_token, requested_action="voice_session:create")

        rel = await db.scalar(select(CareRelationship).where(CareRelationship.elder_id == elder_id))
        rel_id, scopes = rel.id, list(rel.scope)
        # Independent read permission cannot command or replay past successes.
        rel.scope = [s for s in scopes if s != "enrollment:manage"]
        await db.flush()
        assert not (await call("GET", base))["can_manage"]
        await call("POST", base + "/suspend", body, 404, "suspend")
        await db.execute(
            update(CareRelationship).where(CareRelationship.id == rel_id).values(scope=scopes)
        )
        for role in ["ADMIN", "ELDER", "FAMILY_MEMBER", "HOME_CARE_WORKER"]:
            actor = ActorContext(worker_id, role, tenant_id)
            await call("GET", base, expected=404)
        actor = ActorContext(worker_id, "DAYCARE_CARE_WORKER", uuid4())
        await call("GET", base + "/history", expected=404)
        actor = ActorContext(worker_id, "DAYCARE_CARE_WORKER", tenant_id)
        # A suspended enrollment remains administratively visible after its period expires.
        await db.execute(
            update(ElderEnrollment)
            .where(ElderEnrollment.id == enrollment_id)
            .values(valid_from=now - timedelta(days=2), valid_until=now - timedelta(days=1))
        )
        await call("GET", base)
        await call("POST", base + "/resume", {"reason": "Expired", "expected_version": 2}, 409)
        await db.execute(
            update(ElderEnrollment)
            .where(ElderEnrollment.id == enrollment_id)
            .values(valid_until=None)
        )
        resumed = await call("POST", base + "/resume", {"reason": "Return", "expected_version": 2})
        assert resumed["status"] == "ACTIVE" and resumed["version"] == 3
        await call("GET", elder_base + "/profile")
        with pytest.raises(AuthenticationError):
            await service.resolve_current(old_token, requested_action="voice_session:create")
        with pytest.raises(AuthenticationError):
            await service.exchange(old_pairing)
        fresh = await service.issue(actor_context=actor, elder_id=elder_id)
        assert fresh.assisted_session.id != old_session_id
        ended = await call(
            "POST", base + "/end", {"reason": "Service ended", "expected_version": 3}, key="end"
        )
        assert ended["status"] == "ENDED" and ended["ended_at"] and ended["version"] == 4
        await call("POST", base + "/resume", {"reason": "Must fail", "expected_version": 4}, 409)
        with pytest.raises(AuthenticationError):
            await service.exchange(fresh.pairing_token)
        history = await call("GET", base + "/history?limit=2")
        assert history["has_more"]
        history2 = await call("GET", base + "/history?limit=2&cursor=" + history["next_cursor"])
        assert not history2["has_more"] and len(history2["items"]) == 1
        changes = history["items"] + history2["items"]
        assert {h["version"] for h in changes} == {2, 3, 4}
        assert all(h["changed_by_actor_id"] == str(worker_id) for h in changes)
        await call("GET", base + "/history?cursor=invalid", expected=422)
        # Database-enforced immutable history, not just an API convention.
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    update(ElderEnrollmentChange)
                    .where(ElderEnrollmentChange.enrollment_id == enrollment_id)
                    .values(reason="Forbidden")
                )
        assert await db.scalar(select(Elder.status).where(Elder.id == elder_id)) == "ACTIVE"
        assert (
            await db.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.tenant_id == tenant_id,
                    OutboxEvent.event_type == "elder.enrollment_changed.v1",
                )
            )
            == 3
        )
        # Ended controls survive care-data denial, but independently revoked membership does not.
        await db.execute(
            update(ActorTenantMembership)
            .where(ActorTenantMembership.actor_id == worker_id)
            .values(status="INACTIVE")
        )
        await call("GET", base, expected=404)
        await call(
            "POST", base + "/end", {"reason": "Service ended", "expected_version": 3}, 404, "end"
        )
        assert not (await call("GET", "/api/v1/elder-enrollments"))["items"]


@pytest.mark.asyncio(loop_scope="function")
async def test_enrollment_backfill_sql_is_bounded(db_session, monkeypatch):
    # Execute the migration SQL only in a fresh synthetic tenant; never shared grants.
    db = db_session
    now = datetime.now(UTC) - timedelta(hours=1)
    tenant_id, worker_id, unit_id = uuid4(), uuid4(), uuid4()
    db.add_all(
        [
            Tenant(id=tenant_id, name="Synthetic backfill", tenant_type="CARE_ORGANIZATION"),
            Actor(id=worker_id, actor_type="DAYCARE_CARE_WORKER", display_name="Synthetic"),
        ]
    )
    await db.flush()
    db.add(CareUnit(id=unit_id, tenant_id=tenant_id, unit_type="DAYCARE_CENTER", name="Synthetic"))
    await db.flush()
    for uid in [None, unit_id]:
        db.add(
            ActorTenantMembership(
                actor_id=worker_id,
                tenant_id=tenant_id,
                care_unit_id=uid,
                role_code="DAYCARE_CARE_WORKER",
                status="ACTIVE",
                effective_from=now,
            )
        )
    from app.services.elder_onboarding_service import _CREATOR_SCOPE

    old_scopes = [s for s in _CREATOR_SCOPE if not s.startswith("enrollment:")]
    rel_ids = []
    for scopes in [old_scopes, old_scopes[:-1], old_scopes + ["custom:scope"]]:
        elder_id, rel_id = uuid4(), uuid4()
        db.add(
            Elder(
                id=elder_id,
                tenant_id=tenant_id,
                display_name="Synthetic",
                primary_care_setting="DAYCARE",
                status="ACTIVE",
            )
        )
        await db.flush()
        db.add(
            ElderEnrollment(
                elder_id=elder_id,
                tenant_id=tenant_id,
                care_unit_id=unit_id,
                created_by_actor_id=worker_id,
                valid_from=now,
            )
        )
        db.add(
            CareRelationship(
                id=rel_id,
                elder_id=elder_id,
                tenant_id=tenant_id,
                care_unit_id=unit_id,
                actor_id=worker_id,
                relationship_type="DAYCARE_ASSIGNMENT",
                status="ACTIVE",
                effective_from=now,
                scope=scopes,
            )
        )
        rel_ids.append(rel_id)
    await db.flush()
    spec = importlib.util.spec_from_file_location(
        "enrollment_migration",
        Path(__file__).resolve().parents[2]
        / "alembic/versions/20260930_1200_enrollment_lifecycle.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    await db.execute(
        text(module.BACKFILL_SQL + " AND r.tenant_id = :fixture_tenant"),
        {"fixture_tenant": tenant_id},
    )
    found = [
        await db.scalar(select(CareRelationship.scope).where(CareRelationship.id == rid))
        for rid in rel_ids
    ]
    assert set(found[0]) == set(_CREATOR_SCOPE)
    assert found[1] == old_scopes[:-1] and found[2] == old_scopes + ["custom:scope"]
