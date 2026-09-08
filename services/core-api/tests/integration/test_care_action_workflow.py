"""C04/F02 HTTP + PostgreSQL acceptance, using only the disposable test DB.

Identity is injected, but authorization, request transactions, repositories,
row locks, optimistic writes, idempotency and outbox persistence are real.
Candidate setup calls the real promotion service with a synthetic formal event;
this is not browser/login or live Agent-provider E2E evidence.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.exceptions import ValidationError
from app.models.actor import Actor
from app.models.care_action import CareAction, CareActionEventProvenance
from app.models.care_action_candidate import (
    CareActionCandidate,
    CareActionCandidateEventProvenance,
)
from app.models.care_assignment import CareAssignment
from app.models.care_event import CareEvent, CareEventVersion
from app.models.care_unit import CareUnit
from app.models.consent import ConsentGrant
from app.models.elder import Elder
from app.models.idempotency import IdempotencyRecord
from app.models.outbox import OutboxEvent
from app.models.policy import PolicyRegistry
from app.models.tenant import Tenant
from app.schemas.care_event import CreateCareEventCandidateRequest
from app.services.care_action_candidate_service import CareActionCandidateService
from app.services.care_action_service import CareActionService
from app.services.care_event_service import CareEventService
from tests.integration.test_identity_api import _build_client_app

pytestmark = pytest.mark.asyncio


def _proposal(ids):
    return {
        "action_type": "CONTACT_ELDER",
        "suggested_title": "Synthetic contact follow-up",
        "trigger_reason": "Synthetic expected contact was missed",
        "suggested_due_at": ids["due_at"],
        "priority": "MEDIUM",
        "extractor_version": "integration-synthetic-v1",
    }


@pytest_asyncio.fixture
async def care_data(committed_session):
    ids = {
        key: uuid4()
        for key in (
            "tenant",
            "other_tenant",
            "worker",
            "other_worker",
            "family",
            "elder_actor",
            "elder",
            "other_elder",
            "foreign_elder",
            "unit",
            "assignment",
            "event",
            "event_version",
        )
    }
    now = datetime.now(UTC)
    ids["due_at"] = (now + timedelta(days=1)).isoformat()
    committed_session.add_all(
        [
            Tenant(id=ids[key], name="Synthetic Care Tenant", tenant_type="DEMO")
            for key in ("tenant", "other_tenant")
        ]
        + [
            Actor(id=ids[key], actor_type=role, display_name="Synthetic Care Actor")
            for key, role in (
                ("worker", "HOME_CARE_WORKER"),
                ("other_worker", "HOME_CARE_WORKER"),
                ("family", "FAMILY_MEMBER"),
                ("elder_actor", "ELDER"),
            )
        ]
    )
    await committed_session.flush()
    committed_session.add_all(
        [
            Elder(
                id=ids[key],
                tenant_id=ids[tenant],
                display_name="Synthetic Care Elder",
                actor_id=ids["elder_actor"] if key == "elder" else None,
                primary_care_setting="HOME_CARE",
            )
            for key, tenant in (
                ("elder", "tenant"),
                ("other_elder", "tenant"),
                ("foreign_elder", "other_tenant"),
            )
        ]
        + [
            CareUnit(
                id=ids["unit"],
                tenant_id=ids["tenant"],
                name="Synthetic Care Unit",
                unit_type="HOME_CARE_AGENCY",
            )
        ]
    )
    await committed_session.flush()
    committed_session.add(
        CareAssignment(
            id=ids["assignment"],
            tenant_id=ids["tenant"],
            care_unit_id=ids["unit"],
            elder_id=ids["elder"],
            worker_id=ids["worker"],
            service_start=now - timedelta(days=1),
            service_end=now + timedelta(days=1),
            status="CONFIRMED",
            service_scope=["care_action:read", "care_action:create", "care_action:update"],
        )
    )
    event = CareEvent(
        id=ids["event"],
        tenant_id=ids["tenant"],
        elder_id=ids["elder"],
        event_type="EXPECTED_CONTACT_MISSED",
        event_time=now,
        status="VERIFIED",
        current_version=1,
        consent_version=1,
    )
    committed_session.add(event)
    await committed_session.flush()
    version = CareEventVersion(
        event_version_id=ids["event_version"],
        event_id=event.id,
        version=1,
        structured_payload={"synthetic": True},
        evidence_text_ref='["synthetic:evidence"]',
        created_by_actor_id=ids["worker"],
    )
    committed_session.add(version)
    await committed_session.flush()
    candidate = await CareActionCandidateService(
        committed_session, ids["tenant"]
    ).create_from_verified_event(
        event=event, event_version=version, proposal_payload=_proposal(ids)
    )
    ids["candidate"] = candidate.id
    await committed_session.commit()
    return ids


def _client(
    engine,
    ids,
    *,
    actor="worker",
    role="HOME_CARE_WORKER",
    tenant="tenant",
    raise_app_exceptions=True,
):
    app = _build_client_app(engine, ids[actor], role, ids[tenant])
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
        base_url="http://test",
    )


def _actions(ids, elder=None):
    return f"/api/v1/elders/{elder or ids['elder']}/care-actions"


def _candidates(ids, elder=None):
    return f"/api/v1/elders/{elder or ids['elder']}/care-action-candidates"


def _adopt(ids):
    return f"{_candidates(ids)}/{ids['candidate']}/adopt"


def _headers(key=None):
    return {"Idempotency-Key": key or str(uuid4())}


async def test_dashboard_excludes_candidate_and_tracks_adoption_completion(test_engine, care_data):
    ids = care_data
    async with _client(test_engine, ids) as client:
        path = "/api/v1/me/authorized-elders?mode=home-care"
        before = await client.get(path)
        assert before.status_code == 200
        assert before.json()["data"]["items"][0]["open_care_action_count"] == 0
        adopted = await client.post(_adopt(ids), json={"expected_version": 1}, headers=_headers())
        assert adopted.status_code == 200
        action_id = adopted.json()["data"]["adopted_care_action_id"]
        assert (await client.get(path)).json()["data"]["items"][0]["open_care_action_count"] == 1
        completed = await client.patch(
            f"{_actions(ids)}/{action_id}",
            json={"expected_version": 1, "status": "COMPLETED", "resolution": "Synthetic complete"},
            headers=_headers(),
        )
        assert completed.status_code == 200
        assert (await client.get(path)).json()["data"]["items"][0]["open_care_action_count"] == 0


async def test_native_action_proposal_persists_then_http_verify_and_adopt(
    test_engine, care_data, committed_session
):
    """DB regression for datetime JSONB and event updated_at async serialization.

    Setup uses the real persistence service, not the live Agent provider. Only
    CI's disposable DB may execute this test; live browser evidence is separate.
    """
    ids = care_data
    now = datetime.now(UTC)
    policy = PolicyRegistry(
        id=uuid4(),
        owner_tenant_id=ids["tenant"],
        policy_code="synthetic-chain",
        policy_type="CONSENT",
        version="synthetic-v1",
        status="ACTIVE",
        policy_payload={"synthetic_only": True},
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
    proposal = {**_proposal(ids), "suggested_due_at": now + timedelta(days=1)}
    event = await CareEventService(committed_session, ids["tenant"]).create_candidate(
        elder_id=ids["elder"],
        actor_id=ids["elder_actor"],
        request=CreateCareEventCandidateRequest(
            source_type="MANUAL",
            event_type="EXPECTED_CONTACT_MISSED",
            structured_payload={"contact_status": "MISSED"},
            confidence_band="MEDIUM",
            extractor_version="synthetic-chain-v1",
        ),
        trace_id="synthetic-chain",
        idempotency_key="synthetic-chain-event",
        care_action_candidate_proposal=proposal,
    )
    event_id = event.id
    await committed_session.commit()
    async with _client(test_engine, ids, raise_app_exceptions=False) as client:
        path = f"/api/v1/elders/{ids['elder']}/care-events/{event_id}/review"
        headers = _headers()
        request = {"decision": "VERIFY", "reason_code": "SYNTHETIC_QA", "expected_version": 1}
        reviewed = await client.post(path, json=request, headers=headers)
        assert reviewed.status_code == 200, reviewed.text
        result = reviewed.json()["data"]
        assert result["status"] == "VERIFIED" and result["updated_at"]
        replay = await client.post(path, json=request, headers=headers)
        assert replay.status_code == 200 and replay.json()["data"] == result
        candidates = (await client.get(_candidates(ids))).json()["data"]["items"]
        matching = [
            c for c in candidates if c["source_event_provenance"][0]["event_id"] == str(event_id)
        ]
        assert len(matching) == 1
        candidate = matching[0]
        assert candidate["status"] == "PENDING_REVIEW"
        adopted = await client.post(
            f"{_candidates(ids)}/{candidate['care_action_candidate_id']}/adopt",
            json={"expected_version": 1},
            headers=_headers(),
        )
        assert adopted.status_code == 200, adopted.text
        assert adopted.json()["data"]["status"] == "ADOPTED"
        actions = (await client.get(_actions(ids))).json()["data"]["items"]
        assert len(actions) == 1
        assert actions[0]["source_event_provenance"] == candidate["source_event_provenance"]


def _create_body(ids):
    return {
        "action_type": "CONTACT_ELDER",
        "title": "Synthetic manual follow-up",
        "description": "Synthetic private description",
        "trigger_reason": "Synthetic private reason",
        "related_event_ids": [str(ids["event"])],
        "due_at": ids["due_at"],
        "priority": "MEDIUM",
    }


async def _snapshot(engine):
    """Fresh connection reads *all fields*, including claims and provenance.

    committed_session owns isolation/cleanup of this serial disposable-DB suite.
    No mocks, cached ORM objects or counts alone can hide a failed-write mutation.
    """
    async with async_sessionmaker(engine)() as session:
        return {
            model.__tablename__: [
                dict(row)
                for row in (
                    await session.execute(
                        select(model.__table__).order_by(*model.__table__.primary_key)
                    )
                ).mappings()
            ]
            for model in (
                CareAction,
                CareActionEventProvenance,
                CareActionCandidate,
                CareActionCandidateEventProvenance,
                IdempotencyRecord,
                OutboxEvent,
            )
        }


async def _race(engine, model, resource_id, *requests):
    """Prove overlap with PostgreSQL's lock graph, not a scheduling sleep.

    Hold the target row until BOTH requests are blocked (directly, or via the
    first request's idempotency claim). Then release and verify their outcomes.
    Polling and requests are bounded; always cancel/drain tasks before teardown.
    """
    tasks = []
    async with async_sessionmaker(engine)() as lock_session:
        try:
            await lock_session.execute(
                select(model).where(model.id == resource_id).with_for_update()
            )
            blocker = await lock_session.scalar(text("SELECT pg_backend_pid()"))
            tasks = [asyncio.create_task(request) for request in requests]
            async with asyncio.timeout(15):
                async with engine.connect() as observer:
                    while True:
                        waiting = await observer.scalar(
                            text("""
                            WITH RECURSIVE blocked(pid) AS (
                                SELECT pid FROM pg_stat_activity
                                WHERE :blocker = ANY(pg_blocking_pids(pid))
                                UNION
                                SELECT a.pid FROM pg_stat_activity a
                                JOIN blocked b ON b.pid = ANY(pg_blocking_pids(a.pid))
                            ) SELECT count(DISTINCT pid) FROM blocked
                        """),
                            {"blocker": blocker},
                        )
                        # pg_stat_activity is transaction-snapshot cached.
                        await observer.commit()
                        if waiting >= len(requests):
                            break
                        assert not any(
                            task.done() for task in tasks
                        ), "Request ended before row contention"
                        await asyncio.sleep(0.01)
            await lock_session.commit()
            return await asyncio.wait_for(asyncio.gather(*tasks), timeout=15)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await lock_session.rollback()


async def test_adopt_persists_link_provenance_and_minimal_outbox(test_engine, care_data):
    ids = care_data
    before = await _snapshot(test_engine)
    assert not before["care_action"] and not before["outbox_event"]
    async with _client(test_engine, ids) as client:
        pending = (await client.get(_candidates(ids))).json()["data"]["items"]
        assert [row["care_action_candidate_id"] for row in pending] == [str(ids["candidate"])]
        headers = _headers()
        response = await client.post(_adopt(ids), json={"expected_version": 1}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["status"] == "ADOPTED" and body["version"] == 2
        assert body["decided_by_actor_id"] == str(ids["worker"])
        assert body["disposition_reason_code"] == "HUMAN_CONFIRMED"
        replay = await client.post(_adopt(ids), json={"expected_version": 1}, headers=headers)
        assert replay.status_code == 200 and replay.json()["data"] == body
        assert (await client.get(_candidates(ids))).json()["data"]["items"] == []
        actions = (await client.get(_actions(ids))).json()["data"]["items"]
        assert len(actions) == 1
        assert actions[0]["care_action_id"] == body["adopted_care_action_id"]
        assert actions[0]["source_event_provenance"] == body["source_event_provenance"]
    state = await _snapshot(test_engine)
    (action,) = state["care_action"]
    (event,) = state["outbox_event"]
    (claim,) = state["idempotency_record"]
    assert action["created_by_actor_id"] == action["assignee_actor_id"] == ids["worker"]
    assert action["status"] == "OPEN" and action["version"] == 1
    assert len(state["care_action_event_provenance"]) == 1
    assert (
        state["care_action_candidate_event_provenance"]
        == before["care_action_candidate_event_provenance"]
    )
    assert claim["response_body"] == body and claim["status"] == "COMPLETED"
    assert event["event_type"] == "care.action.created.v1"
    assert event["aggregate_id"] == action["care_action_id"]
    assert event["tenant_id"] == ids["tenant"] and event["elder_id"] == ids["elder"]
    assert event["actor_id"] == ids["worker"] and event["classification"] == "CONFIDENTIAL"
    assert set(event["payload"]) == {
        "care_action_id",
        "action_type",
        "assignee_actor_id",
        "related_event_ids",
        "source_event_provenance",
        "due_at",
        "priority",
        "status",
        "version",
    }
    assert set(event["payload"]["source_event_provenance"][0]) == {
        "event_id",
        "event_version_id",
        "event_version",
        "snapshot_sha256",
        "snapshot_schema_version",
    }


@pytest.mark.parametrize("terminal", ["COMPLETED", "CANCELLED"])
async def test_manual_lifecycle_and_immutable_replay(test_engine, care_data, terminal):
    ids = care_data
    async with _client(test_engine, ids) as client:
        create_headers = _headers()
        body = _create_body(ids)
        created = await client.post(_actions(ids), json=body, headers=create_headers)
        assert created.status_code == 201, created.text
        original = created.json()["data"]
        path = f"{_actions(ids)}/{original['care_action_id']}"
        start_headers = _headers()
        start = {"status": "IN_PROGRESS", "expected_version": 1}
        started = await client.patch(path, json=start, headers=start_headers)
        assert started.status_code == 200, started.text
        postponed = await client.patch(
            path,
            json={
                "status": "POSTPONED",
                "expected_version": 2,
                "resolution": "Synthetic postponement",
                "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            },
            headers=_headers(),
        )
        assert postponed.status_code == 200, postponed.text
        finished = await client.patch(
            path,
            json={
                "status": terminal,
                "expected_version": 3,
                "resolution": "Synthetic resolution",
            },
            headers=_headers(),
        )
        assert finished.status_code == 200 and finished.json()["data"]["version"] == 4
        state = await _snapshot(test_engine)
        replay = await client.post(_actions(ids), json=body, headers=create_headers)
        assert replay.status_code == 201 and replay.json()["data"] == original
        replay = await client.patch(path, json=start, headers=start_headers)
        assert replay.status_code == 200 and replay.json()["data"] == started.json()["data"]
        conflict = await client.post(
            _actions(ids), json={**body, "title": "Changed payload"}, headers=create_headers
        )
        assert conflict.status_code == 409
        invalid = await client.patch(
            path, json={"status": "IN_PROGRESS", "expected_version": 4}, headers=_headers()
        )
        assert invalid.status_code == 409
        assert await _snapshot(test_engine) == state
    assert state["care_action"][0]["status"] == terminal
    assert len(state["care_action_event_provenance"]) == 1
    assert sorted(row["aggregate_version"] for row in state["outbox_event"]) == [1, 2, 3, 4]


@pytest.mark.parametrize("decision,status", [("REJECT", "REJECTED"), ("EXCLUDE", "EXCLUDED")])
async def test_dismiss_replay_has_no_formal_action_or_outbox(
    test_engine, care_data, decision, status
):
    ids = care_data
    async with _client(test_engine, ids) as client:
        path = f"{_candidates(ids)}/{ids['candidate']}/dismiss"
        headers = _headers()
        body = {
            "decision": decision,
            "expected_version": 1,
            "reason_code": "NOT_NEEDED",
            "notes": "Synthetic human decision",
        }
        response = await client.post(path, json=body, headers=headers)
        assert response.status_code == 200, response.text
        state = await _snapshot(test_engine)
        (candidate,) = state["care_action_candidate"]
        assert candidate["status"] == status and candidate["version"] == 2
        assert candidate["disposition_reason_code"] == "NOT_NEEDED"
        assert candidate["disposition_notes"] == body["notes"]
        assert candidate["decided_by_actor_id"] == ids["worker"] and candidate["decided_at"]
        assert not state["care_action"] and not state["outbox_event"]
        replay = await client.post(path, json=body, headers=headers)
        assert replay.status_code == 200 and replay.json()["data"] == response.json()["data"]
        adopt = await client.post(_adopt(ids), json={"expected_version": 2}, headers=_headers())
        assert adopt.status_code == 409
        assert await _snapshot(test_engine) == state


@pytest.mark.parametrize("same_key", [True, False])
async def test_concurrent_adoption_creates_exactly_one_action(test_engine, care_data, same_key):
    ids = care_data
    first = _headers()
    second = first if same_key else _headers()
    async with _client(test_engine, ids) as client:
        results = await _race(
            test_engine,
            CareActionCandidate,
            ids["candidate"],
            client.post(_adopt(ids), json={"expected_version": 1}, headers=first),
            client.post(_adopt(ids), json={"expected_version": 1}, headers=second),
        )
    assert sorted(r.status_code for r in results) == ([200, 200] if same_key else [200, 409])
    if same_key:
        assert results[0].json()["data"] == results[1].json()["data"]
    state = await _snapshot(test_engine)
    assert (
        len(state["care_action"])
        == len(state["outbox_event"])
        == len(state["idempotency_record"])
        == 1
    )
    assert state["care_action_candidate"][0]["version"] == 2
    assert (
        state["care_action_candidate"][0]["adopted_care_action_id"]
        == state["care_action"][0]["care_action_id"]
    )


async def test_concurrent_state_updates_have_one_winner(test_engine, care_data):
    ids = care_data
    async with _client(test_engine, ids) as client:
        created = await client.post(_actions(ids), json=_create_body(ids), headers=_headers())
        assert created.status_code == 201, created.text
        action_id = UUID(created.json()["data"]["care_action_id"])
        path = f"{_actions(ids)}/{action_id}"
        results = await _race(
            test_engine,
            CareAction,
            action_id,
            *[
                client.patch(
                    path,
                    json={"status": status, "expected_version": 1, "resolution": "Synthetic race"},
                    headers=_headers(),
                )
                for status in ("COMPLETED", "CANCELLED")
            ],
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(r.json()["data"] for r in results if r.status_code == 200)
    state = await _snapshot(test_engine)
    assert state["care_action"][0]["status"] == winner["status"]
    assert state["care_action"][0]["version"] == 2
    assert len(state["outbox_event"]) == len(state["idempotency_record"]) == 2


async def test_concurrent_adopt_and_dismiss_share_one_decision(test_engine, care_data):
    ids = care_data
    async with _client(test_engine, ids) as client:
        results = await _race(
            test_engine,
            CareActionCandidate,
            ids["candidate"],
            client.post(_adopt(ids), json={"expected_version": 1}, headers=_headers()),
            client.post(
                f"{_candidates(ids)}/{ids['candidate']}/dismiss",
                json={"expected_version": 1, "decision": "REJECT", "reason_code": "NOT_NEEDED"},
                headers=_headers(),
            ),
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(r.json()["data"] for r in results if r.status_code == 200)
    state = await _snapshot(test_engine)
    assert state["care_action_candidate"][0]["status"] == winner["status"]
    assert state["care_action_candidate"][0]["version"] == 2
    expected_actions = 1 if winner["status"] == "ADOPTED" else 0
    assert len(state["care_action"]) == len(state["outbox_event"]) == expected_actions
    assert len(state["idempotency_record"]) == 1


@pytest.mark.parametrize("source_scope", ["other_elder", "foreign_elder", "unreviewed"])
async def test_manual_create_rejects_existing_nonformal_or_cross_scope_source(
    test_engine, care_data, source_scope
):
    ids = care_data
    async with async_sessionmaker(test_engine)() as session, session.begin():
        source = CareEvent(
            tenant_id=ids["other_tenant"] if source_scope == "foreign_elder" else ids["tenant"],
            elder_id=ids["elder"] if source_scope == "unreviewed" else ids[source_scope],
            event_type="EXPECTED_CONTACT_MISSED",
            event_time=datetime.now(UTC),
            status="CANDIDATE" if source_scope == "unreviewed" else "VERIFIED",
            current_version=1,
            consent_version=1,
        )
        session.add(source)
        await session.flush()
        source_id = source.id
        session.add(
            CareEventVersion(
                event_id=source_id,
                version=1,
                structured_payload={"synthetic": True},
                created_by_actor_id=ids["worker"],
            )
        )
    before = await _snapshot(test_engine)
    async with _client(test_engine, ids) as client:
        response = await client.post(
            _actions(ids),
            json={**_create_body(ids), "related_event_ids": [str(source_id)]},
            headers=_headers(),
        )
        assert response.status_code == 422, response.text
    assert await _snapshot(test_engine) == before


@pytest.mark.parametrize(
    "stale", ["candidate_version", "source_version", "source_status", "past_due"]
)
async def test_failed_adoption_rolls_back_candidate_version_and_claim(
    test_engine, care_data, stale
):
    ids = care_data
    if stale in {"source_version", "source_status"}:
        async with async_sessionmaker(test_engine)() as session, session.begin():
            event = await session.get(CareEvent, ids["event"])
            if stale == "source_version":
                session.add(
                    CareEventVersion(
                        event_id=event.id,
                        version=2,
                        structured_payload={"synthetic": "corrected"},
                        created_by_actor_id=ids["worker"],
                    )
                )
                await session.flush()
                event.current_version = 2
                event.status = "CORRECTED"
            else:
                event.status = "REJECTED"
    before = await _snapshot(test_engine)
    body = {"expected_version": 9 if stale == "candidate_version" else 1}
    if stale == "past_due":
        body["due_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    async with _client(test_engine, ids) as client:
        result = await client.post(_adopt(ids), json=body, headers=_headers())
    assert result.status_code == (409 if stale.endswith("version") else 422), result.text
    assert await _snapshot(test_engine) == before


async def test_outbox_failure_rolls_back_entire_adoption_and_allows_retry(
    test_engine, care_data, monkeypatch
):
    ids = care_data
    before = await _snapshot(test_engine)
    original = CareActionService._write_event

    async def fail_after_real_outbox_insert(self, **kwargs):
        await original(self, **kwargs)
        await self._session.flush()
        # Real PostgreSQL failure after action/provenance/outbox have been flushed.
        await self._session.execute(text("SELECT 1 / 0"))

    headers = _headers()
    async with _client(test_engine, ids, raise_app_exceptions=False) as client:
        with monkeypatch.context() as patch:
            patch.setattr(CareActionService, "_write_event", fail_after_real_outbox_insert)
            failed = await client.post(_adopt(ids), json={"expected_version": 1}, headers=headers)
        assert failed.status_code == 500
        assert await _snapshot(test_engine) == before
        retry = await client.post(_adopt(ids), json={"expected_version": 1}, headers=headers)
        assert retry.status_code == 200, retry.text
    after = await _snapshot(test_engine)
    assert (
        len(after["care_action"])
        == len(after["outbox_event"])
        == len(after["idempotency_record"])
        == 1
    )


@pytest.mark.parametrize("endpoint", ["create", "adopt", "dismiss", "update"])
async def test_expired_assignment_blocks_even_completed_replay(test_engine, care_data, endpoint):
    ids = care_data
    headers = _headers()
    method, path, body = "POST", _actions(ids), _create_body(ids)
    async with _client(test_engine, ids) as client:
        if endpoint == "adopt":
            path, body = _adopt(ids), {"expected_version": 1}
        elif endpoint == "dismiss":
            path = f"{_candidates(ids)}/{ids['candidate']}/dismiss"
            body = {"expected_version": 1, "decision": "REJECT", "reason_code": "NOT_NEEDED"}
        elif endpoint == "update":
            created = await client.post(path, json=body, headers=_headers())
            assert created.status_code == 201, created.text
            method, path = "PATCH", f"{path}/{created.json()['data']['care_action_id']}"
            body = {"status": "IN_PROGRESS", "expected_version": 1}
        response = await client.request(method, path, json=body, headers=headers)
        assert response.status_code in {200, 201}, response.text
        before = await _snapshot(test_engine)
        async with async_sessionmaker(test_engine)() as session, session.begin():
            assignment = await session.get(CareAssignment, ids["assignment"])
            assignment.service_end = datetime.now(UTC) - timedelta(hours=1)
        for attempt_headers in (headers, _headers()):
            denied = await client.request(method, path, json=body, headers=attempt_headers)
            assert denied.status_code == 404, denied.text
        for listing in (_actions(ids), _candidates(ids)):
            assert (await client.get(listing)).status_code == 404
        assert await _snapshot(test_engine) == before


@pytest.mark.parametrize("scope", ["other_elder", "foreign_elder", "missing"])
async def test_cross_scope_ids_do_not_reveal_or_mutate_candidate(test_engine, care_data, scope):
    ids = care_data
    before = await _snapshot(test_engine)
    target = uuid4() if scope == "missing" else ids[scope]
    async with _client(test_engine, ids) as client:
        path = f"{_candidates(ids, target)}/{ids['candidate']}/adopt"
        denied = await client.post(path, json={"expected_version": 1}, headers=_headers())
        missing = await client.post(
            f"{_candidates(ids)}/{uuid4()}/adopt", json={"expected_version": 1}, headers=_headers()
        )
        assert denied.status_code == missing.status_code == 404
        denied_error, missing_error = denied.json()["error"], missing.json()["error"]
        assert denied_error.pop("correlation_id")
        assert missing_error.pop("correlation_id")
        assert denied_error == missing_error
        for listing in (_actions(ids, target), _candidates(ids, target)):
            assert (await client.get(listing)).status_code == 404
    assert await _snapshot(test_engine) == before


@pytest.mark.parametrize(
    "actor,role",
    [("elder_actor", "ELDER"), ("family", "FAMILY_MEMBER"), ("other_worker", "HOME_CARE_WORKER")],
)
async def test_nonprofessional_or_unassigned_actor_has_zero_side_effects(
    test_engine, care_data, actor, role
):
    ids = care_data
    before = await _snapshot(test_engine)
    async with _client(test_engine, ids, actor=actor, role=role) as client:
        for path, body in (
            (_actions(ids), _create_body(ids)),
            (_adopt(ids), {"expected_version": 1}),
            (
                f"{_candidates(ids)}/{ids['candidate']}/dismiss",
                {"decision": "REJECT", "expected_version": 1, "reason_code": "NOT_NEEDED"},
            ),
        ):
            denied = await client.post(path, json=body, headers=_headers())
            assert denied.status_code == 404, denied.text
    assert await _snapshot(test_engine) == before


@pytest.mark.parametrize("title", ["請長者停藥", "請調整藥物劑量", "診斷疾病", "Change medication"])
async def test_medical_proposal_cannot_create_candidate_or_formal_side_effects(
    test_engine, care_data, title
):
    ids = care_data
    before = await _snapshot(test_engine)
    async with async_sessionmaker(test_engine)() as session, session.begin():
        event = await session.get(CareEvent, ids["event"])
        version = await session.get(CareEventVersion, ids["event_version"])
        with pytest.raises(ValidationError) as error:
            await CareActionCandidateService(session, ids["tenant"]).create_from_verified_event(
                event=event,
                event_version=version,
                proposal_payload={**_proposal(ids), "suggested_title": title},
            )
        assert error.value.details == [
            {"field": "proposal", "reason": "MEDICAL_ACTION_NOT_ALLOWED"}
        ]
        # Commit even after the caught validation error to detect accidental writes.
    assert await _snapshot(test_engine) == before


@pytest.mark.parametrize("invalid", ["medical_type", "other_assignee", "missing_source"])
async def test_invalid_manual_command_does_not_leave_claim_or_outbox(
    test_engine, care_data, invalid
):
    ids = care_data
    body = _create_body(ids)
    if invalid == "medical_type":
        body["action_type"] = "CHANGE_MEDICATION"
    elif invalid == "other_assignee":
        body["assignee_actor_id"] = str(ids["other_worker"])
    else:
        body["related_event_ids"] = [str(uuid4())]
    before = await _snapshot(test_engine)
    async with _client(test_engine, ids) as client:
        result = await client.post(_actions(ids), json=body, headers=_headers())
        assert result.status_code == 422, result.text
    assert await _snapshot(test_engine) == before
