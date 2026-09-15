"""Real PostgreSQL correction transactions; disposable CI database only."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.care_assignment import CareAssignment
from app.models.care_event import CareEvent, CareEventVersion, ReviewDecision
from app.models.consent import ConsentGrant
from app.models.outbox import OutboxEvent
from app.models.policy import PolicyRegistry
from app.models.summary import DailySummary, SummaryVersion
from app.schemas.care_event import CreateCareEventCandidateRequest
from app.services import care_event_service
from app.services.care_event_service import CareEventService
from tests.integration import test_care_action_workflow as care_fixtures
from tests.integration.test_care_action_workflow import _client, _headers

care_data = care_fixtures.care_data

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(loop_scope="function")
async def correction_data(care_data, committed_session):
    ids = dict(care_data)
    now = datetime.now(UTC)
    policy = PolicyRegistry(
        id=uuid4(),
        owner_tenant_id=ids["tenant"],
        policy_code="correction-test",
        policy_type="CONSENT",
        version="v1",
        status="ACTIVE",
        policy_payload={},
        effective_from=now - timedelta(days=1),
    )
    committed_session.add(policy)
    await committed_session.flush()
    committed_session.add(
        ConsentGrant(
            elder_id=ids["elder"],
            purpose_code="CARE_EVENT_EXTRACTION",
            status="GRANTED",
            version=1,
            scope={},
            granted_by_actor_id=ids["elder_actor"],
            policy_id=policy.id,
            granted_at=now,
            effective_at=now - timedelta(minutes=1),
        )
    )
    assignment = await committed_session.get(CareAssignment, ids["assignment"])
    assignment.service_scope = [*assignment.service_scope, "care_event:read", "care_event:review"]
    await committed_session.flush()
    event = await CareEventService(committed_session, ids["tenant"]).create_candidate(
        elder_id=ids["elder"],
        actor_id=ids["worker"],
        request=CreateCareEventCandidateRequest(
            source_type="MANUAL",
            event_type="MEAL",
            event_time=now,
            structured_payload={"text": "Synthetic original"},
            confidence_band="MEDIUM",
            extractor_version="test",
        ),
        trace_id="correction-test",
        idempotency_key=str(uuid4()),
    )
    ids["correct_event"] = event.id
    ids["old_time"] = now
    # Synthetic legacy reference exercises invalidation even for an existing non-formal source.
    summary = DailySummary(
        elder_id=ids["elder"],
        tenant_id=ids["tenant"],
        summary_date=now.date(),
        summary_type="PROFESSIONAL_DAILY",
        status="READY",
        current_version=1,
    )
    committed_session.add(summary)
    await committed_session.flush()
    committed_session.add(
        SummaryVersion(summary_id=summary.id, version=1, content={}, source_event_ids=[event.id])
    )
    ids["summary"] = summary.id
    await committed_session.commit()
    return ids


def _path(ids):
    return f"/api/v1/elders/{ids['elder']}/care-events/{ids['correct_event']}/review"


def _request(**extra):
    return {
        "decision": "CORRECT",
        "reason_code": "SYNTHETIC_CORRECTION",
        "expected_version": 1,
        "corrected_payload": {"text": "Synthetic corrected"},
        "corrected_event_type": "SLEEP",
        **extra,
    }


async def test_correct_clear_audit_replay_conflict_and_expiry(test_engine, correction_data):
    ids = correction_data
    headers = _headers()
    payload = _request(corrected_event_time=None)
    async with _client(test_engine, ids, raise_app_exceptions=False) as client:
        response = await client.post(_path(ids), json=payload, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["event_type"] == "SLEEP" and data["event_time"] is None and data["version"] == 2
        assert (await client.post(_path(ids), json=payload, headers=headers)).json()["data"] == data
        # Omitted means preserve; it must not replay the earlier explicit-clear command.
        assert (await client.post(_path(ids), json=_request(), headers=headers)).status_code == 409
        assert (await client.post(_path(ids), json=payload, headers=_headers())).status_code == 409
        async with async_sessionmaker(test_engine, expire_on_commit=False)() as db:
            review = await db.get(ReviewDecision, UUID(data["review_record_id"]))
            assert (review.before_event_type, review.after_event_type) == ("MEAL", "SLEEP")
            assert review.before_event_time == ids["old_time"] and review.after_event_time is None
            versions = (
                (
                    await db.execute(
                        select(CareEventVersion)
                        .where(CareEventVersion.event_id == ids["correct_event"])
                        .order_by(CareEventVersion.version)
                    )
                )
                .scalars()
                .all()
            )
            assert len(versions) == 2 and versions[0].structured_payload == {
                "text": "Synthetic original"
            }
            assert versions[1].supersedes_version_id == versions[0].event_version_id
            assert (await db.get(DailySummary, ids["summary"])).status == "STALE"
            rows = (
                (
                    await db.execute(
                        select(OutboxEvent).where(
                            OutboxEvent.aggregate_id == ids["correct_event"],
                            OutboxEvent.event_type == "care.event.corrected.v1",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 1
            assignment = await db.get(CareAssignment, ids["assignment"])
            assignment.service_end = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()
        assert (await client.post(_path(ids), json=payload, headers=headers)).status_code == 404


async def test_concurrent_corrections_have_one_winner(test_engine, correction_data):
    ids = correction_data
    async with (
        _client(test_engine, ids, raise_app_exceptions=False) as a,
        _client(test_engine, ids, raise_app_exceptions=False) as b,
    ):
        responses = await asyncio.gather(
            a.post(
                _path(ids),
                json=_request(corrected_event_time="2026-09-14T20:00:00Z"),
                headers=_headers(),
            ),
            b.post(_path(ids), json=_request(corrected_event_time=None), headers=_headers()),
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    async with async_sessionmaker(test_engine)() as db:
        assert (
            len(
                (
                    await db.execute(
                        select(ReviewDecision).where(
                            ReviewDecision.event_id == ids["correct_event"]
                        )
                    )
                )
                .scalars()
                .all()
            )
            == 1
        )


async def test_outbox_failure_rolls_back_metadata_audit_and_summary(
    test_engine, correction_data, monkeypatch
):
    ids = correction_data
    original = care_event_service.write_outbox_entry

    async def fail_after_insert(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("Synthetic failure")

    monkeypatch.setattr(care_event_service, "write_outbox_entry", fail_after_insert)
    headers = _headers()
    async with _client(test_engine, ids, raise_app_exceptions=False) as client:
        response = await client.post(
            _path(ids), json=_request(corrected_event_time=None), headers=headers
        )
        assert response.status_code == 500
        async with async_sessionmaker(test_engine)() as db:
            event = await db.get(CareEvent, ids["correct_event"])
            assert (
                event.event_type == "MEAL"
                and event.event_time == ids["old_time"]
                and event.current_version == 1
            )
            assert (await db.get(DailySummary, ids["summary"])).status == "READY"
            assert (
                not (
                    await db.execute(
                        select(ReviewDecision).where(ReviewDecision.event_id == event.id)
                    )
                )
                .scalars()
                .all()
            )
            assert (
                len(
                    (
                        await db.execute(
                            select(CareEventVersion).where(CareEventVersion.event_id == event.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                == 1
            )
        monkeypatch.setattr(care_event_service, "write_outbox_entry", original)
        retry = await client.post(_path(ids), json=_request(), headers=headers)
        assert retry.status_code == 200, retry.text
        data = retry.json()["data"]
        assert datetime.fromisoformat(data["event_time"]) == ids["old_time"]
        async with async_sessionmaker(test_engine)() as db:
            review = await db.get(ReviewDecision, UUID(data["review_record_id"]))
            assert review.before_event_time == review.after_event_time == ids["old_time"]


@pytest.mark.parametrize("actor", ["other_worker", "family"])
async def test_unauthorized_correction_has_no_metadata_write(test_engine, correction_data, actor):
    ids = correction_data
    async with _client(
        test_engine,
        ids,
        actor=actor,
        role="FAMILY_MEMBER" if actor == "family" else "HOME_CARE_WORKER",
        raise_app_exceptions=False,
    ) as client:
        assert (
            await client.post(_path(ids), json=_request(), headers=_headers())
        ).status_code == 404
    async with async_sessionmaker(test_engine)() as db:
        event = await db.get(CareEvent, ids["correct_event"])
        assert event.event_type == "MEAL" and event.current_version == 1


@pytest.mark.parametrize("scope", ["other_elder", "foreign_elder", "other_tenant"])
async def test_cross_scope_correction_is_hidden(test_engine, correction_data, scope):
    ids = correction_data
    target = {**ids, "elder": ids[scope]} if scope != "other_tenant" else ids
    async with _client(
        test_engine, ids, tenant="other_tenant" if scope == "other_tenant" else "tenant"
    ) as client:
        assert (
            await client.post(_path(target), json=_request(), headers=_headers())
        ).status_code == 404
    async with async_sessionmaker(test_engine)() as db:
        event = await db.get(CareEvent, ids["correct_event"])
        assert event.event_type == "MEAL" and event.current_version == 1
