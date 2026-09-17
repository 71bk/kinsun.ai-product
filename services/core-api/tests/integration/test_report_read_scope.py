"""Report scope narrowing against real SQL and HTTP in the disposable test DB.

Identity and the request session are injected; authorization and repositories are real.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import reports
from app.api.error_handlers import register_exception_handlers
from app.core.auth import ActorContext
from app.models.actor import Actor
from app.models.care_relationship import CareRelationship
from app.models.consent import ConsentGrant
from app.models.elder import Elder
from app.models.policy import PolicyRegistry
from app.models.report import FamilyRelationship, FamilyReport, ReportVersion
from app.models.tenant import Tenant


@pytest.mark.asyncio
async def test_current_share_scope_controls_list_and_detail(db_session):
    db = db_session
    tenant_id, elder_id, elder_actor, family_actor, policy_id, consent_id = (
        uuid4() for _ in range(6)
    )
    now = datetime.now(UTC)
    db.add_all(
        [
            Tenant(id=tenant_id, name="Synthetic report tenant", tenant_type="DEMO"),
            Actor(id=elder_actor, actor_type="ELDER", display_name="Synthetic elder"),
            Actor(id=family_actor, actor_type="FAMILY_MEMBER", display_name="Synthetic family"),
        ]
    )
    await db.flush()
    db.add_all(
        [
            Elder(
                id=elder_id,
                tenant_id=tenant_id,
                actor_id=elder_actor,
                display_name="Synthetic elder",
                primary_care_setting="INDEPENDENT",
            ),
            PolicyRegistry(
                id=policy_id,
                owner_tenant_id=tenant_id,
                policy_code="synthetic-report",
                policy_type="CONSENT",
                version="1",
                status="ACTIVE",
                policy_payload={},
                effective_from=now - timedelta(days=1),
            ),
        ]
    )
    await db.flush()
    db.add(
        ConsentGrant(
            id=consent_id,
            elder_id=elder_id,
            purpose_code="FAMILY_SHARING",
            version=1,
            policy_id=policy_id,
            granted_by_actor_id=elder_actor,
            granted_at=now,
            effective_at=now - timedelta(hours=1),
        )
    )
    await db.flush()
    relationship = FamilyRelationship(
        elder_id=elder_id,
        family_actor_id=family_actor,
        consent_id=consent_id,
        share_scope=["REPORT_ALL"],
        effective_from=now - timedelta(hours=1),
    )
    db.add_all(
        [
            relationship,
            CareRelationship(
                elder_id=elder_id,
                actor_id=family_actor,
                tenant_id=tenant_id,
                relationship_type="FAMILY_SHARE",
                scope=["family_report:read"],
                effective_from=now - timedelta(hours=1),
            ),
        ]
    )
    await db.flush()
    report = FamilyReport(
        elder_id=elder_id,
        tenant_id=tenant_id,
        report_type="DAILY",
        status="PUBLISHED",
        period_start=date.today(),
        period_end=date.today(),
        published_at=now,
        recipient_scope={"relationship_ids": [str(relationship.id)]},
    )
    db.add(report)
    await db.flush()
    db.add(
        ReportVersion(
            report_id=report.id,
            version=1,
            content={"items": []},
            share_scope_snapshot=report.recipient_scope,
        )
    )
    await db.flush()
    app = FastAPI()
    app.include_router(reports.router)
    register_exception_handlers(app)
    actor = ActorContext(actor_id=family_actor, tenant_id=tenant_id, actor_role="FAMILY_MEMBER")
    app.dependency_overrides[reports.require_active_actor] = lambda: actor
    app.dependency_overrides[reports.get_db_session] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listing = f"/api/v1/family/elders/{elder_id}/reports"
        detail = f"/api/v1/family/reports/{report.id}"
        assert (await client.get(detail)).status_code == 200
        assert len((await client.get(listing)).json()["data"]["items"]) == 1
        relationship.share_scope = ["REPORT_WEEKLY"]
        await db.flush()
        assert (await client.get(detail)).status_code == 404
        assert (await client.get(listing)).json()["data"]["items"] == []
        relationship.share_scope = ["REPORT_DAILY"]
        await db.flush()
        assert (await client.get(detail)).status_code == 200
        actor = ActorContext(actor_id=uuid4(), tenant_id=tenant_id, actor_role="FAMILY_MEMBER")
        assert (await client.get(detail)).status_code == 404
        actor = ActorContext(actor_id=family_actor, tenant_id=uuid4(), actor_role="FAMILY_MEMBER")
        assert (await client.get(detail)).status_code == 404
