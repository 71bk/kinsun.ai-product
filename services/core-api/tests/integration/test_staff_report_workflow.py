"""Synthetic staff draft -> review -> family read workflow; transaction owned by fixture."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import reports, staff_reports
from app.api.error_handlers import register_exception_handlers
from app.core.auth import ActorContext
from app.models.actor import Actor
from app.models.care_assignment import CareAssignment
from app.models.care_event import CareEvent
from app.models.care_relationship import CareRelationship
from app.models.care_unit import CareUnit
from app.models.consent import ConsentGrant
from app.models.elder import Elder
from app.models.policy import PolicyRegistry
from app.models.report import FamilyRelationship
from app.models.summary import DailySummary, SummaryVersion
from app.models.tenant import Tenant


@pytest.mark.asyncio
async def test_staff_report_lifecycle_and_live_guards(db_session):
    db = db_session
    tenant, elder, owner, family, worker, unit, policy = [uuid4() for _ in range(7)]
    now = datetime.now(UTC)
    db.add_all(
        [
            Tenant(id=tenant, name="Synthetic report workflow", tenant_type="DEMO"),
            Actor(id=owner, actor_type="ELDER", display_name="Synthetic elder"),
            Actor(id=family, actor_type="FAMILY_MEMBER", display_name="Synthetic family"),
            Actor(id=worker, actor_type="HOME_CARE_WORKER", display_name="Synthetic worker"),
        ]
    )
    await db.flush()
    db.add_all(
        [
            Elder(
                id=elder,
                tenant_id=tenant,
                actor_id=owner,
                display_name="Synthetic elder",
                primary_care_setting="HOME_CARE",
            ),
            CareUnit(
                id=unit, tenant_id=tenant, unit_type="HOME_CARE_AGENCY", name="Synthetic unit"
            ),
            PolicyRegistry(
                id=policy,
                owner_tenant_id=tenant,
                policy_code="synthetic-report-workflow",
                policy_type="CONSENT",
                version="1",
                status="ACTIVE",
                policy_payload={},
                effective_from=now - timedelta(days=1),
            ),
        ]
    )
    await db.flush()
    sharing = ConsentGrant(
        elder_id=elder,
        purpose_code="FAMILY_SHARING",
        version=1,
        policy_id=policy,
        granted_by_actor_id=owner,
        granted_at=now,
        effective_at=now - timedelta(hours=1),
    )
    extraction = ConsentGrant(
        elder_id=elder,
        purpose_code="CARE_EVENT_EXTRACTION",
        version=1,
        policy_id=policy,
        granted_by_actor_id=owner,
        granted_at=now,
        effective_at=now - timedelta(hours=1),
    )
    assignment = CareAssignment(
        tenant_id=tenant,
        elder_id=elder,
        worker_id=worker,
        care_unit_id=unit,
        status="IN_PROGRESS",
        service_start=now - timedelta(hours=1),
        service_end=now + timedelta(hours=1),
        service_scope=[
            "family_report:draft:create",
            "family_report:publish",
            "family_report:withdraw",
            "summary:read",
        ],
    )
    db.add_all([sharing, extraction, assignment])
    await db.flush()
    relationship = FamilyRelationship(
        elder_id=elder,
        family_actor_id=family,
        consent_id=sharing.id,
        share_scope=["REPORT_DAILY"],
        effective_from=now - timedelta(hours=1),
    )
    event = CareEvent(
        tenant_id=tenant, elder_id=elder, event_type="MEAL", status="VERIFIED", consent_version=1
    )
    summary = DailySummary(
        tenant_id=tenant,
        elder_id=elder,
        summary_date=date.today(),
        summary_type="PROFESSIONAL_DAILY",
        status="READY",
        current_version=1,
    )
    db.add_all(
        [
            relationship,
            event,
            summary,
            CareRelationship(
                tenant_id=tenant,
                elder_id=elder,
                actor_id=family,
                relationship_type="FAMILY_SHARE",
                scope=["family_report:read"],
                effective_from=now - timedelta(hours=1),
            ),
        ]
    )
    await db.flush()
    db.add(
        SummaryVersion(
            summary_id=summary.id,
            version=1,
            source_event_ids=[event.id],
            content={
                "items": [
                    {
                        "category": "MEAL",
                        "text": "合成飲食紀錄：早餐吃粥。",
                        "source_event_ids": [str(event.id)],
                        "data_status": "PRESENT",
                    }
                ],
                "missing_fields": ["SLEEP"],
                "conflict_flags": [],
            },
        )
    )
    await db.flush()
    app = FastAPI()
    app.include_router(staff_reports.router)
    app.include_router(reports.router)
    register_exception_handlers(app)
    actor = ActorContext(actor_id=worker, actor_role="HOME_CARE_WORKER", tenant_id=tenant)
    staff = actor
    app.dependency_overrides[staff_reports.require_active_actor] = lambda: actor
    app.dependency_overrides[staff_reports.get_db_session] = lambda: db
    base = f"/api/v1/elders/{elder}"
    create_body = {
        "summary_id": str(summary.id),
        "expected_summary_version": 1,
        "recipient_scope_ids": [str(relationship.id)],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

        async def post(path, body, key=None):
            return await client.post(
                base + path, json=body, headers={"Idempotency-Key": key or str(uuid4())}
            )

        workspace = await client.get(base + "/family-report-workspace")
        assert workspace.status_code == 200, workspace.text
        assert workspace.json()["data"]["recipients"][0]["display_name"] == "Synthetic family"
        assert "email" not in workspace.text
        assert (
            await post("/family-reports/from-summary", {**create_body, "items": []})
        ).status_code == 422
        assert (
            await post(
                "/family-reports/from-summary", {**create_body, "expected_summary_version": 2}
            )
        ).status_code == 409
        summary.status = "NEEDS_REVIEW"
        await db.flush()
        assert (await post("/family-reports/from-summary", create_body)).status_code == 409
        summary.status = "READY"
        await db.flush()
        key = str(uuid4())
        created = await post("/family-reports/from-summary", create_body, key)
        assert created.status_code == 201, created.text
        report = created.json()["data"]
        report_id = report["report_id"]
        assert report["status"] == "NEEDS_REVIEW"
        assert report["items"][0]["text"] == "合成飲食紀錄：早餐吃粥。"
        assert report["items"][0]["source_ids"] == [str(summary.id)]
        assert report["data_gap_notice"]
        assert (await post("/family-reports/from-summary", create_body, key)).json()["data"][
            "report_id"
        ] == report_id
        actor = ActorContext(actor_id=family, actor_role="FAMILY_MEMBER", tenant_id=tenant)
        family_url = f"/api/v1/family/reports/{report_id}"
        assert (await client.get(family_url)).status_code == 404
        assert (await client.get(base + "/family-report-workspace")).status_code == 404
        actor = ActorContext(actor_id=owner, actor_role="ELDER", tenant_id=tenant)
        assert (await post("/family-reports/from-summary", create_body)).status_code == 404
        actor = staff
        publish_path = f"/family-reports/{report_id}/publish"
        publish = {
            "expected_version": 1,
            "safety_review_passed": True,
            "reason_code": "SYNTHETIC_HUMAN_REVIEW",
        }
        assert (
            await post(publish_path, {**publish, "safety_review_passed": False})
        ).status_code == 422
        assert (await post(publish_path, {**publish, "expected_version": 9})).status_code == 409
        summary.current_version = 2
        await db.flush()
        assert (await post(publish_path, publish)).status_code == 409
        summary.current_version = 1
        relationship.share_scope = ["REPORT_WEEKLY"]
        await db.flush()
        assert (await post(publish_path, publish)).status_code == 422
        assert (await client.get(base + "/family-report-workspace")).json()["data"][
            "recipients"
        ] == []
        relationship.share_scope = ["REPORT_DAILY"]
        sharing.status = "REVOKED"
        sharing.revoked_at = now
        await db.flush()
        assert (await post(publish_path, publish)).status_code == 404
        assert (await client.get(base + "/family-report-workspace")).status_code == 404
        sharing.status = "GRANTED"
        sharing.revoked_at = None
        await db.flush()
        extraction.status = "REVOKED"
        extraction.revoked_at = now
        await db.flush()
        assert (await post(publish_path, publish)).status_code == 404
        extraction.status = "GRANTED"
        extraction.revoked_at = None
        event.status = "REJECTED"
        await db.flush()
        assert (await post(publish_path, publish)).status_code == 422
        event.status = "VERIFIED"
        await db.flush()
        old_scopes = assignment.service_scope
        assignment.service_scope = ["summary:read"]
        await db.flush()
        assert (await post(publish_path, publish)).status_code == 404
        assignment.service_scope = old_scopes
        await db.flush()
        actor = ActorContext(actor_id=worker, actor_role="HOME_CARE_WORKER", tenant_id=uuid4())
        assert (await post(publish_path, publish)).status_code == 404
        actor = staff
        publish_key = str(uuid4())
        published = await post(publish_path, publish, publish_key)
        assert published.status_code == 200, published.text
        assert published.json()["data"]["status"] == "PUBLISHED"
        assert (await post(publish_path, publish, publish_key)).status_code == 200
        actor = ActorContext(actor_id=family, actor_role="FAMILY_MEMBER", tenant_id=tenant)
        visible = await client.get(family_url)
        assert visible.status_code == 200, visible.text
        assert "source_summary_versions" not in visible.text
        assert visible.json()["data"]["items"][0]["text"] == report["items"][0]["text"]
        actor = staff
        withdrawn = await post(
            f"/family-reports/{report_id}/withdraw",
            {"expected_version": 1, "reason_code": "SYNTHETIC_WITHDRAWAL"},
        )
        assert withdrawn.status_code == 200, withdrawn.text
        assert withdrawn.json()["data"]["status"] == "WITHDRAWN"
        assert (await post(publish_path, publish)).status_code == 409
        actor = ActorContext(actor_id=family, actor_role="FAMILY_MEMBER", tenant_id=tenant)
        assert (await client.get(family_url)).status_code == 404
