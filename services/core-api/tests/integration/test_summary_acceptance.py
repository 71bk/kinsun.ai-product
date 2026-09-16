"""B02 regression cases for the disposable CI database only.

Actor identity is injected; SQL, authorization, transactions and outbox are real.
This is not browser, login or evidence-snippet acceptance.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.care_assignment import CareAssignment
from app.models.care_event import CareEvent, CareEventVersion
from app.models.outbox import OutboxEvent
from app.models.summary import DailySummary, SummaryVersion
from tests.integration import test_event_metadata_correction as correction_fixtures
from tests.integration.test_care_action_workflow import _client, _headers

care_data = correction_fixtures.care_data
correction_data = correction_fixtures.correction_data
pytestmark = pytest.mark.asyncio
DAY = "2026-08-14"
START = datetime(2026, 8, 13, 16, tzinfo=UTC)
END = START + timedelta(days=1)


@pytest_asyncio.fixture(loop_scope="function")
async def summary_data(correction_data, committed_session):
    ids = dict(correction_data)
    assignment = await committed_session.get(CareAssignment, ids["assignment"])
    assignment.service_scope = [
        *assignment.service_scope,
        "summary:read",
        "summary:review",
        "summary:rebuild",
    ]
    await committed_session.commit()
    return ids


async def _event(
    db, ids, when, *, created_at=None, status="VERIFIED", elder="elder", tenant="tenant"
):
    event = CareEvent(
        tenant_id=ids[tenant],
        elder_id=ids[elder],
        source_type="MANUAL",
        event_type="MEAL",
        event_time=when,
        created_at=created_at or START,
        status=status,
        current_version=1,
        consent_version=1,
    )
    db.add(event)
    await db.flush()
    db.add(
        CareEventVersion(
            event_id=event.id,
            version=1,
            structured_payload={"text": "Synthetic meal"},
            evidence_text_ref='["synthetic:evidence"]',
        )
    )
    await db.flush()
    return event.id


def _summaries(ids):
    return f"/api/v1/elders/{ids['elder']}/summaries"


@pytest.mark.parametrize(
    "scope", ["other_worker", "family", "other_tenant", "other_elder", "foreign_elder"]
)
async def test_generation_does_not_expand_authorization(test_engine, summary_data, scope):
    ids = summary_data
    target = {**ids, "elder": ids[scope]} if scope in {"other_elder", "foreign_elder"} else ids
    async with _client(
        test_engine,
        ids,
        actor=scope if scope in {"family", "other_worker"} else "worker",
        role="FAMILY_MEMBER" if scope == "family" else "HOME_CARE_WORKER",
        tenant="other_tenant" if scope == "other_tenant" else "tenant",
    ) as client:
        assert (await _generate(client, target)).status_code == 404


async def _generate(client, ids, headers=None):
    return await client.post(
        f"{_summaries(ids)}/generate", json={"summary_date": DAY}, headers=headers or _headers()
    )


async def _snapshot(db, summary_id):
    summary = await db.get(DailySummary, summary_id)
    versions = (
        await db.scalars(
            select(SummaryVersion)
            .where(SummaryVersion.summary_id == summary_id)
            .order_by(SummaryVersion.version)
        )
    ).all()
    outbox_count = await db.scalar(
        select(func.count()).select_from(OutboxEvent).where(OutboxEvent.aggregate_id == summary_id)
    )
    return summary.status, summary.current_version, [v.content for v in versions], outbox_count


async def test_taipei_boundaries_fallback_and_source_lookup(test_engine, summary_data):
    ids = summary_data
    async with async_sessionmaker(test_engine)() as db:
        expected = [
            await _event(db, ids, START),
            await _event(db, ids, END - timedelta(microseconds=1)),
            await _event(db, ids, None, created_at=START + timedelta(hours=1)),
        ]
        # Event time takes precedence even when recorded on a different day.
        expected.append(await _event(db, ids, START + timedelta(hours=2), created_at=END))
        for when in (START - timedelta(microseconds=1), END):
            await _event(db, ids, when)
        await _event(db, ids, None, created_at=END)
        for status in ("CANDIDATE", "NEEDS_REVIEW", "REJECTED", "EXCLUDED", "DELETED"):
            await _event(db, ids, START, status=status)
        await _event(db, ids, START, elder="other_elder")
        await _event(db, ids, START, elder="foreign_elder", tenant="other_tenant")
        await db.commit()
    async with _client(test_engine, ids) as client:
        response = await _generate(client, ids)
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["status"] == "NEEDS_REVIEW"
        assert [item["source_event_ids"][0] for item in data["items"]] == [
            str(expected[i]) for i in (0, 2, 3, 1)
        ]
        for item in data["items"]:
            event_id = item["source_event_ids"][0]
            source = await client.get(f"/api/v1/elders/{ids['elder']}/care-events/{event_id}")
            assert source.status_code == 200, source.text
            assert source.json()["data"]["structured_payload"] == {"text": "Synthetic meal"}
            assert source.json()["data"]["evidence_refs"] == ["synthetic:evidence"]
            wrong_elder = await client.get(
                f"/api/v1/elders/{ids['other_elder']}/care-events/{event_id}"
            )
            assert wrong_elder.status_code == 404
        formal = await client.get(_summaries(ids), params={"date": DAY})
        assert formal.json()["data"]["items"] == []


async def test_overflow_preserves_existing_summary_and_outbox(test_engine, summary_data):
    ids = summary_data
    async with async_sessionmaker(test_engine)() as db:
        for _ in range(32):
            await _event(db, ids, START)
        await db.commit()
    async with _client(test_engine, ids) as client:
        response = await _generate(client, ids)
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert len(data["items"]) == 32
        summary_id = UUID(data["summary_id"])
        async with async_sessionmaker(test_engine)() as db:
            before = await _snapshot(db, summary_id)
            await _event(db, ids, START)
            await db.commit()
        key = _headers()
        for _ in range(2):
            rejected = await _generate(client, ids, key)
            assert rejected.status_code == 422, rejected.text
            assert rejected.json()["error"]["details"] == [
                {"field": "summary_date", "reason": "SUMMARY_EVENT_LIMIT_EXCEEDED"}
            ]
        async with async_sessionmaker(test_engine)() as db:
            assert await _snapshot(db, summary_id) == before


async def test_correction_then_explicit_regeneration_uses_current_version(
    test_engine, summary_data
):
    ids = summary_data
    async with async_sessionmaker(test_engine)() as db:
        source_id = await _event(db, ids, START, status="NEEDS_REVIEW")
        await db.commit()
    async with _client(test_engine, ids) as client:
        initial = await _generate(client, ids)
        assert initial.status_code == 201, initial.text
        initial_data = initial.json()["data"]
        assert initial_data["items"] == []
        source_path = f"/api/v1/elders/{ids['elder']}/care-events/{source_id}"
        corrected = await client.post(
            f"{source_path}/review",
            headers=_headers(),
            json={
                "decision": "CORRECT",
                "expected_version": 1,
                "reason_code": "SYNTHETIC",
                "corrected_event_type": "SLEEP",
                "corrected_event_time": "2026-08-14T00:00:00+08:00",
                "corrected_payload": {"text": "Synthetic corrected sleep"},
            },
        )
        assert corrected.status_code == 200, corrected.text
        key = _headers()
        generated = await _generate(client, ids, key)
        assert generated.status_code == 201, generated.text
        data = generated.json()["data"]
        assert data["summary_id"] == initial_data["summary_id"]
        assert data["version"] == 2 and data["status"] == "NEEDS_REVIEW"
        assert data["items"] == [
            {
                "category": "SLEEP",
                "text": "睡眠陳述：Synthetic corrected sleep",
                "source_event_ids": [str(source_id)],
                "data_status": "PRESENT",
            }
        ]
        assert "SLEEP" not in data["missing_fields"]
        assert (await _generate(client, ids, key)).json()["data"] == data
        async with async_sessionmaker(test_engine)() as db:
            snapshot = await _snapshot(db, UUID(data["summary_id"]))
            assert snapshot[1] == 2 and snapshot[3] == 2
            assert snapshot[2][0]["items"] == []
            source_versions = (
                await db.scalars(
                    select(CareEventVersion)
                    .where(CareEventVersion.event_id == source_id)
                    .order_by(CareEventVersion.version)
                )
            ).all()
            assert [v.structured_payload for v in source_versions] == [
                {"text": "Synthetic meal"},
                {"text": "Synthetic corrected sleep"},
            ]
            assignment = await db.get(CareAssignment, ids["assignment"])
            assignment.service_end = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()
        assert (await _generate(client, ids, key)).status_code == 404
        assert (await client.get(source_path)).status_code == 404


async def test_rebuild_only_marks_stale_until_explicit_generation(test_engine, summary_data):
    ids = summary_data
    async with _client(test_engine, ids) as client:
        generated = await _generate(client, ids)
        assert generated.status_code == 201, generated.text
        data = generated.json()["data"]
        path = f"{_summaries(ids)}/{data['summary_id']}"
        key = _headers()
        payload = {"expected_version": 1, "reason_code": "SYNTHETIC_REBUILD"}
        rebuilt = await client.post(f"{path}/rebuild", headers=key, json=payload)
        assert rebuilt.status_code == 200, rebuilt.text
        stale = rebuilt.json()["data"]
        assert stale["status"] == "STALE" and stale["version"] == 1
        assert (await client.post(f"{path}/rebuild", headers=key, json=payload)).json()[
            "data"
        ] == stale
        regenerated = await _generate(client, ids)
        assert regenerated.status_code == 201, regenerated.text
        assert regenerated.json()["data"]["version"] == 2
        assert regenerated.json()["data"]["status"] == "NEEDS_REVIEW"
        assert (
            await client.post(f"{path}/rebuild", headers=_headers(), json=payload)
        ).status_code == 409
        async with async_sessionmaker(test_engine)() as db:
            snapshot = await _snapshot(db, UUID(data["summary_id"]))
            assert snapshot[1] == 2 and snapshot[3] == 3
