"""Real SQL/HTTP profile maintenance; caller owns a rollback-only transaction."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select, update

from app.core.auth import ActorContext
from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.middleware.actor_guard import require_active_actor
from app.models.actor import Actor
from app.models.care_profile import ElderCareProfileEntry
from app.models.care_relationship import CareRelationship
from app.models.care_unit import CareUnit
from app.models.elder_enrollment import ElderEnrollment
from app.models.elder_profile_change import ElderProfileChange
from app.models.membership import ActorTenantMembership
from app.models.outbox import OutboxEvent
from app.models.tenant import Tenant


@pytest.mark.asyncio(loop_scope="function")
async def test_profile_http_lifecycle(db_session, monkeypatch):
    # Onboarding is opt-in; CI must not depend on a developer's .env flag.
    monkeypatch.setattr(get_settings(), "assisted_elder_sessions_enabled", True)
    db = db_session
    now = datetime.now(UTC)
    tenant = Tenant(id=uuid4(), name="Synthetic profile workflow", tenant_type="CARE_ORGANIZATION")
    worker = Actor(id=uuid4(), actor_type="DAYCARE_CARE_WORKER", display_name="Synthetic staff")
    db.add_all([tenant, worker])
    await db.flush()
    unit = CareUnit(
        id=uuid4(), tenant_id=tenant.id, unit_type="DAYCARE_CENTER", name="Synthetic unit"
    )
    db.add(unit)
    await db.flush()
    for unit_id in [None, unit.id]:
        db.add(
            ActorTenantMembership(
                actor_id=worker.id,
                tenant_id=tenant.id,
                care_unit_id=unit_id,
                role_code="DAYCARE_CARE_WORKER",
                status="ACTIVE",
                effective_from=now - timedelta(minutes=1),
                effective_to=now + timedelta(hours=1),
            )
        )
    await db.flush()
    actor = ActorContext(worker.id, worker.actor_type, tenant.id)
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
            assert response.status_code == expected, f"{method} status {response.status_code}"
            if expected < 300 and "/organizations/" not in path:
                assert response.headers["cache-control"] == "no-store"
            return response.json().get("data") if expected < 300 else response.json()

        created = await call(
            "POST",
            f"/api/v1/organizations/{tenant.id}/elders",
            {"display_name": "Synthetic elder", "care_unit_id": str(unit.id)},
            201,
        )
        elder_id = UUID(created["elder_id"])
        base = f"/api/v1/elders/{elder_id}"
        profile = await call("GET", base + "/profile")
        assert profile["profile_version"] == 1
        basic_body = {
            "display_name": "Corrected synthetic name",
            "preferred_name": "Synthetic name",
            "preferred_language": "NAN_TW",
            "expected_version": 1,
            "reason": "Name correction",
        }
        changed = await call("PATCH", base + "/profile", basic_body, key="profile-basic")
        assert changed["profile_version"] == 2
        assert await call("PATCH", base + "/profile", basic_body, key="profile-basic") == changed
        await call("PATCH", base + "/profile", basic_body, 409)
        await call(
            "PATCH",
            base + "/profile",
            {**basic_body, "display_name": "Different"},
            409,
            "profile-basic",
        )
        await call("PATCH", base + "/profile", {**basic_body, "actor_id": str(worker.id)}, 422)
        care_body = {
            "category": "ALLERGY",
            "content": "Synthetic first record",
            "reason": "Initial record",
        }
        entry = await call("POST", base + "/care-profile", care_body, 201, "profile-create")
        assert await call("POST", base + "/care-profile", care_body, 201, "profile-create") == entry
        assert entry["verification_status"] == "RECORDED"
        entry_path = base + "/care-profile/" + entry["care_profile_entry_id"]
        # A clinical verification never survives a staff correction.
        await db.execute(
            update(ElderCareProfileEntry)
            .where(ElderCareProfileEntry.id == UUID(entry["care_profile_entry_id"]))
            .values(source_type="CLINICAL_DOCUMENT", verification_status="VERIFIED")
        )
        updated = await call(
            "PATCH",
            entry_path,
            {**care_body, "content": "Synthetic correction", "expected_version": 1},
        )
        assert updated["version"] == 2 and updated["verification_status"] == "RECORDED"
        assert updated["source_type"] == "STAFF_RECORDED"
        await call("PATCH", entry_path, {**care_body, "expected_version": 1}, 409)
        retired = await call(
            "POST", entry_path + "/retire", {"expected_version": 2, "reason": "No longer used"}
        )
        assert retired["version"] == 3 and retired["retired_at"]
        assert not (await call("GET", base + "/care-profile"))["items"]
        assert len((await call("GET", base + "/care-profile?include_retired=true"))["items"]) == 1
        await call("PATCH", entry_path, {**care_body, "expected_version": 3}, 409)
        await call("POST", entry_path + "/retire", {"expected_version": 3, "reason": "Again"}, 409)
        history = await call("GET", base + "/profile-history?limit=2")
        assert history["has_more"] and len(history["items"]) == 2
        older = await call(
            "GET", base + "/profile-history?limit=2&cursor=" + history["next_cursor"]
        )
        assert not older["has_more"]
        all_changes = history["items"] + older["items"]
        assert len({h["profile_change_id"] for h in all_changes}) == 4
        correction = next(h for h in all_changes if h["change_type"] == "CARE_ENTRY_UPDATED")
        assert correction["before_data"]["verification_status"] == "VERIFIED"
        assert correction["before_data"]["content"] == "Synthetic first record"
        assert correction["after_data"]["content"] == "Synthetic correction"
        assert all(
            h["changed_by_actor_id"] == str(worker.id)
            and h["changed_by_name"] == worker.display_name
            for h in all_changes
        )
        await call("GET", base + "/care-profile?cursor=invalid", expected=422)
        await call("GET", base + "/profile-history?limit=101", expected=422)
        # Read permission does not grant write, including replay of an older success.
        rel = await db.scalar(select(CareRelationship).where(CareRelationship.elder_id == elder_id))
        scopes = list(rel.scope)
        # Execute the migration's actual scope backfill inside this synthetic
        # tenant only; no DDL, downgrade, or shared tenant mutation.
        spec = importlib.util.spec_from_file_location(
            "profile_migration",
            Path(__file__).resolve().parents[2]
            / "alembic/versions/20260929_1800_elder_profile_history.py",
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        migration.op = MagicMock()
        migration.upgrade()
        from sqlalchemy import text

        backfill = text(
            str(migration.op.execute.call_args.args[0]) + " AND r.tenant_id = :fixture_tenant"
        )
        old_defaults = [
            s
            for s in scopes
            if s
            not in {
                "elder:profile:update",
                "care_profile:write",
                "enrollment:read",
                "enrollment:manage",
            }
        ]
        # now() in migration SQL is the outer transaction's start time.
        # Model a pre-existing enrollment rather than one created later in it.
        rel.effective_from = now - timedelta(minutes=1)
        enrollment = await db.scalar(
            select(ElderEnrollment).where(ElderEnrollment.elder_id == elder_id)
        )
        enrollment.valid_from = now - timedelta(minutes=1)
        rel.scope = old_defaults
        await db.flush()
        await db.execute(backfill, {"fixture_tenant": tenant.id})
        await db.refresh(rel)
        assert set(rel.scope) == set(scopes) - {"enrollment:read", "enrollment:manage"}
        rel.scope = old_defaults[:-1]
        await db.flush()
        await db.execute(backfill, {"fixture_tenant": tenant.id})
        await db.refresh(rel)
        assert rel.scope == old_defaults[:-1]
        rel.scope = [s for s in scopes if s not in {"elder:profile:update", "care_profile:write"}]
        await db.flush()
        await call("GET", base + "/profile")
        await call("PATCH", base + "/profile", basic_body, 404, "profile-basic")
        await call("POST", base + "/care-profile", care_body, 404, "profile-create")
        # Family, elder, admin and foreign tenant remain non-disclosing even with scopes.
        for role in ["FAMILY_MEMBER", "ELDER", "ADMIN"]:
            actor = ActorContext(worker.id, role, tenant.id)
            await call("GET", base + "/profile", expected=404)
            await call("GET", base + "/profile-history", expected=404)
        actor = ActorContext(worker.id, worker.actor_type, uuid4())
        await call("GET", base + "/care-profile", expected=404)
        actor = ActorContext(worker.id, worker.actor_type, tenant.id)
        rel.scope = scopes
        enrollment = await db.scalar(
            select(ElderEnrollment).where(ElderEnrollment.elder_id == elder_id)
        )
        enrollment.status = "SUSPENDED"
        await db.flush()
        await call("GET", base + "/profile", expected=404)
        await call("PATCH", base + "/profile", basic_body, 404, "profile-basic")
        enrollment.status = "ACTIVE"
        rel.effective_to = datetime.now(UTC)
        await db.flush()
        await call("GET", base + "/profile", expected=404)
        await call("GET", f"/api/v1/elders/{uuid4()}/profile", expected=404)
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ElderProfileChange)
                .where(ElderProfileChange.elder_id == elder_id)
            )
            == 4
        )
        events = list(
            (
                await db.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.tenant_id == tenant.id,
                        OutboxEvent.event_type == "elder.profile_changed.v1",
                    )
                )
            ).scalars()
        )
        assert len(events) == 4
        assert all(
            set(event.payload)
            == {
                "profile_change_id",
                "elder_id",
                "care_profile_entry_id",
                "change_type",
                "resource_version",
            }
            for event in events
        )
        rel.effective_to = None
        for index in range(20):
            db.add(
                ElderCareProfileEntry(
                    tenant_id=tenant.id,
                    elder_id=elder_id,
                    category="CARE_PRECAUTION",
                    content="Synthetic bounded entry",
                    source_actor_id=worker.id,
                    source_type="STAFF_RECORDED",
                    verification_status="DISPUTED" if index == 0 else "RECORDED",
                    version=1,
                )
            )
        await db.flush()
        await call("POST", base + "/care-profile", care_body, 409)
        disputed = await db.scalar(
            select(ElderCareProfileEntry).where(
                ElderCareProfileEntry.elder_id == elder_id,
                ElderCareProfileEntry.verification_status == "DISPUTED",
            )
        )
        disputed_path = base + "/care-profile/" + str(disputed.id)
        await call("PATCH", disputed_path, {**care_body, "expected_version": 1}, 409)
        await call(
            "POST",
            disputed_path + "/retire",
            {"expected_version": 1, "reason": "Disputed information withdrawn"},
        )
        await call("POST", base + "/care-profile", care_body, 201)
