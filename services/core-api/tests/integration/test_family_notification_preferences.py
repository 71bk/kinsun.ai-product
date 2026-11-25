"""Two synthetic families; HTTP commands, real SQL guards, no LINE network.

The caller owns the transaction. This function can also run in the private
outer-rollback QA runner without loading destructive integration conftest.
"""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api import family_notification_preferences as api
from app.api.error_handlers import register_exception_handlers
from app.core.auth import ActorContext
from app.models.actor import Actor
from app.models.care_relationship import CareRelationship
from app.models.consent import ConsentGrant
from app.models.elder import Elder
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.notification import NotificationPreference
from app.models.outbox import OutboxEvent
from app.models.policy import PolicyRegistry
from app.models.report import FamilyRelationship, FamilyReport, ReportVersion
from app.models.tenant import Tenant
from app.repositories.notification_repo import NotificationRepository
from app.services.line_subject_cipher import LineSubjectCipher


@pytest.mark.asyncio
async def test_family_preferences_http_sql_lifecycle(db_session):
    db = db_session
    tenant_id, elder_id, owner_id, first_id, second_id = [uuid4() for _ in range(5)]
    now = datetime.now(UTC)
    secret = "synthetic-line-notification-destination-secret-32-bytes"
    cipher = LineSubjectCipher(secret)
    tenant = Tenant(id=tenant_id, name="Synthetic notification tenant", tenant_type="DEMO")
    families = [
        Actor(id=actor_id, actor_type="FAMILY_MEMBER", display_name="Synthetic family")
        for actor_id in (first_id, second_id)
    ]
    db.add_all(
        [tenant, Actor(id=owner_id, actor_type="ELDER", display_name="Synthetic elder"), *families]
    )
    await db.flush()
    elder = Elder(
        id=elder_id,
        tenant_id=tenant_id,
        actor_id=owner_id,
        display_name="Synthetic elder",
        primary_care_setting="HOME_CARE",
    )
    policy = PolicyRegistry(
        owner_tenant_id=tenant_id,
        policy_code="synthetic-line-preference",
        policy_type="CONSENT",
        version="1",
        status="ACTIVE",
        policy_payload={},
        effective_from=now - timedelta(days=1),
    )
    db.add_all([elder, policy])
    await db.flush()
    consent = ConsentGrant(
        elder_id=elder_id,
        purpose_code="FAMILY_SHARING",
        version=1,
        policy_id=policy.id,
        granted_by_actor_id=owner_id,
        granted_at=now,
        effective_at=now - timedelta(days=1),
        scope={"share_scopes": ["REPORT_DAILY"]},
    )
    db.add(consent)
    await db.flush()
    relationships, memberships, scopes = [], [], []
    for i, actor_id in enumerate((first_id, second_id)):
        relationships.append(
            FamilyRelationship(
                elder_id=elder_id,
                family_actor_id=actor_id,
                consent_id=consent.id,
                share_scope=["REPORT_DAILY"],
                effective_from=now - timedelta(days=1),
            )
        )
        memberships.append(
            ActorTenantMembership(
                tenant_id=tenant_id,
                actor_id=actor_id,
                role_code="FAMILY_MEMBER",
                effective_from=now - timedelta(days=1),
            )
        )
        scopes.append(
            CareRelationship(
                tenant_id=tenant_id,
                elder_id=elder_id,
                actor_id=actor_id,
                relationship_type="FAMILY_SHARE",
                scope=["family_report:read"],
                effective_from=now - timedelta(days=1),
            )
        )
        db.add(
            ExternalIdentity(
                provider="LINE",
                actor_id=actor_id,
                external_subject_digest=str(i + 1) * 64,
                digest_key_version=1,
                encrypted_external_subject=cipher.encrypt(f"UsyntheticFamily{i}"),
            )
        )
    db.add_all([*relationships, *memberships, *scopes])
    await db.flush()
    report = FamilyReport(
        tenant_id=tenant_id,
        elder_id=elder_id,
        report_type="DAILY",
        period_start=date(2026, 10, 12),
        period_end=date(2026, 10, 12),
        status="PUBLISHED",
        published_at=now,
        recipient_scope={"relationship_ids": [str(row.id) for row in relationships]},
    )
    db.add(report)
    await db.flush()
    db.add(
        ReportVersion(
            report_id=report.id,
            version=1,
            content={"items": []},
            share_scope_snapshot={"relationship_ids": [str(row.id) for row in relationships]},
        )
    )
    await db.flush()
    actor = ActorContext(first_id, "FAMILY_MEMBER", tenant_id)
    settings = SimpleNamespace(
        line_daily_notification_enabled=True,
        line_account_link_enabled=True,
        line_subject_encryption_secret=secret,
    )
    app = FastAPI()
    app.include_router(api.router)
    register_exception_handlers(app)
    app.dependency_overrides[api.require_active_actor] = lambda: actor
    app.dependency_overrides[api.get_db_session] = lambda: db
    app.dependency_overrides[api.get_settings] = lambda: settings
    path = f"/api/v1/family/elders/{elder_id}/line-notification-preference"

    async def candidates():
        rows = await NotificationRepository(db, tenant_id).list_daily_line_candidates(
            source_date=date(2026, 10, 12),
            now=datetime.now(UTC),
            timezone="Asia/Taipei",
            send_time=time(8),
        )
        return {row.recipient_actor_id for row in rows}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

        async def put(enabled, version, key=None, extra=None):
            return await client.put(
                path,
                json={"line_enabled": enabled, "expected_version": version, **(extra or {})},
                headers={"Idempotency-Key": key or str(uuid4())},
            )

        initial = await client.get(path)
        assert initial.status_code == 200
        assert initial.json()["data"]["version"] == 0
        assert initial.json()["data"]["can_enable"]
        assert (
            await db.scalar(
                select(func.count())
                .select_from(NotificationPreference)
                .where(NotificationPreference.elder_id == elder_id)
            )
            == 0
        )
        assert (await put(True, 0, extra={"family_actor_id": str(second_id)})).status_code == 422
        key = str(uuid4())
        enabled = await put(True, 0, key)
        assert enabled.status_code == 200
        snapshot = enabled.json()["data"]
        assert snapshot["line_enabled"] and snapshot["version"] == 1
        assert (await put(True, 0, key)).json()["data"] == snapshot
        assert (await put(False, 0, key)).status_code == 409
        assert (await put(False, 0)).status_code == 409
        assert await candidates() == {first_id}
        actor = ActorContext(second_id, "FAMILY_MEMBER", tenant_id)
        assert (await client.get(path)).json()["data"]["version"] == 0
        assert (await put(True, 0, key)).status_code == 200  # key scoped to this actor
        assert await candidates() == {first_id, second_id}
        actor = ActorContext(first_id, "FAMILY_MEMBER", tenant_id)
        row = await db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.family_actor_id == first_id,
                NotificationPreference.elder_id == elder_id,
            )
        )
        row.channels = ["LINE", "EMAIL"]
        row.send_time_local = None
        await db.flush()
        assert (await client.get(path)).json()["data"]["availability"] == "UNSUPPORTED_SCHEDULE"
        assert (await put(True, 1)).status_code == 409
        settings.line_daily_notification_enabled = False
        disabled = await put(False, 1)
        assert disabled.status_code == 200 and disabled.json()["data"]["version"] == 2
        assert row.channels == ["EMAIL"]
        assert await candidates() == {second_id}
        settings.line_daily_notification_enabled = True
        events = list(
            (await db.scalars(select(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id))).all()
        )
        assert len(events) == 3
        assert all(
            event.event_type == "family.notification_preference.updated.v1" for event in events
        )
        assert all(set(event.payload) == {"line_enabled", "version"} for event in events)
        assert (
            "encrypted_external_subject" not in disabled.text
            and "UsyntheticFamily" not in disabled.text
        )
        actor = ActorContext(first_id, "FAMILY_MEMBER", uuid4())
        assert (await client.get(path)).status_code == 404
        actor = ActorContext(first_id, "ADMIN", tenant_id)
        assert (await client.get(path)).status_code == 404
        actor = ActorContext(first_id, "FAMILY_MEMBER", tenant_id)
        # Each live guard also denies an otherwise valid idempotency replay.
        changes = [
            (memberships[0], "effective_to", now - timedelta(seconds=1)),
            (relationships[0], "effective_to", now - timedelta(seconds=1)),
            (relationships[0], "share_scope", ["REPORT_WEEKLY"]),
            (scopes[0], "scope", ["elder:basic:read"]),
            (consent, "expires_at", now - timedelta(seconds=1)),
            (families[0], "status", "SUSPENDED"),
        ]
        for entity, field, value in changes:
            previous = getattr(entity, field)
            setattr(entity, field, value)
            await db.flush()
            assert (await client.get(path)).status_code == 404, field
            assert (await put(True, 0, key)).status_code == 404, field
            setattr(entity, field, previous)
            await db.flush()
        relationships[1].effective_to = now - timedelta(seconds=1)
        await db.flush()
        assert await candidates() == set()
        assert (await client.get(path)).json()["data"]["line_enabled"] is False
