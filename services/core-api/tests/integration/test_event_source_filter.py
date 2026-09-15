"""B04 source filtering using synthetic data and disposable PostgreSQL only."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.care_assignment import CareAssignment
from app.models.care_event import CareEvent, CareEventVersion
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.schemas.care_event import CreateCareEventCandidateRequest
from app.services.care_event_service import CareEventService
from app.services.summary_service import SummaryService
from tests.integration import test_event_metadata_correction as correction_fixtures
from tests.integration.test_care_action_workflow import _client, _headers

care_data = correction_fixtures.care_data
correction_data = correction_fixtures.correction_data
pytestmark = pytest.mark.asyncio
ANCHOR = datetime(2026, 8, 1, 8, tzinfo=UTC)


@pytest_asyncio.fixture(loop_scope="function")
async def source_data(correction_data, committed_session):
    ids = dict(correction_data)
    consent = await committed_session.scalar(
        select(ConsentGrant).where(ConsentGrant.elder_id == ids["elder"])
    )
    conversation = ConversationSession(
        elder_id=ids["elder"],
        tenant_id=ids["tenant"],
        initiator_type="ELDER",
        initiator_actor_id=ids["elder_actor"],
        language_route="ZH_TW",
        state="COMPLETED",
        trace_id=str(uuid4()),
        consent_id=consent.id,
        consent_version=1,
    )
    committed_session.add(conversation)
    await committed_session.flush()
    ids["session"] = conversation.id
    ids["expected"] = {source: [] for source in ("MANUAL", "CONVERSATION_SESSION", "UNKNOWN")}
    # Interleave sources at an identical timestamp to exercise UUID tie-breaking.
    for source in ids["expected"]:
        for index in range(5):
            event = CareEvent(
                elder_id=ids["elder"],
                tenant_id=ids["tenant"],
                event_type="MEAL",
                source_type="MANUAL" if source == "MANUAL" else None,
                source_session_id=conversation.id if source == "CONVERSATION_SESSION" else None,
                event_time=ANCHOR,
                created_at=ANCHOR,
                status="VERIFIED",
                consent_version=1,
                current_version=1,
            )
            committed_session.add(event)
            await committed_session.flush()
            version = CareEventVersion(
                event_id=event.id, version=1, structured_payload={"text": "Synthetic meal"}
            )
            committed_session.add(version)
            await committed_session.flush()
            if index == 0:
                event.current_version = 2
                event.status = "CORRECTED"
                committed_session.add(
                    CareEventVersion(
                        event_id=event.id,
                        version=2,
                        structured_payload={"text": "Synthetic corrected meal"},
                        supersedes_version_id=version.event_version_id,
                    )
                )
            ids["expected"][source].append(str(event.id))
    # Higher-ranked mismatches cannot consume the first filtered page.
    for elder, tenant, kind, when, status in (
        ("other_elder", "tenant", "MEAL", ANCHOR, "VERIFIED"),
        ("foreign_elder", "other_tenant", "MEAL", ANCHOR, "VERIFIED"),
        ("elder", "tenant", "SLEEP", ANCHOR, "VERIFIED"),
        ("elder", "tenant", "MEAL", ANCHOR + timedelta(days=1), "VERIFIED"),
        ("elder", "tenant", "MEAL", ANCHOR, "DELETED"),
    ):
        event = CareEvent(
            elder_id=ids[elder],
            tenant_id=ids[tenant],
            source_type="MANUAL",
            event_type=kind,
            event_time=when,
            created_at=ANCHOR + timedelta(minutes=1),
            status=status,
            consent_version=1,
            current_version=1,
        )
        committed_session.add(event)
        await committed_session.flush()
        committed_session.add(CareEventVersion(event_id=event.id, version=1, structured_payload={}))
    await committed_session.commit()
    return ids


def _path(ids):
    return f"/api/v1/elders/{ids['elder']}/care-events"


async def _pages(client, ids, source=None):
    params = {"event_type": "MEAL", "date_from": "2026-08-01", "date_to": "2026-08-01", "limit": 2}
    if source is not None:
        params["source_type"] = source
    found = []
    cursors = set()
    for _ in range(20):
        response = await client.get(_path(ids), params=params)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        found.extend(item["event_id"] for item in data["items"])
        if not data["has_more"]:
            assert data["next_cursor"] is None
            return found
        assert len(data["items"]) == 2 and data["next_cursor"] not in cursors
        cursors.add(data["next_cursor"])
        params["cursor"] = data["next_cursor"]
    pytest.fail("Pagination did not terminate")


@pytest.mark.parametrize("source", [None, "MANUAL", "CONVERSATION_SESSION", "UNKNOWN"])
async def test_source_pagination_combines_filters_without_duplicates(
    test_engine, source_data, source
):
    ids = source_data
    expected = ids["expected"][source] if source else sum(ids["expected"].values(), [])
    async with _client(test_engine, ids) as client:
        assert await _pages(client, ids, source) == sorted(expected, reverse=True)


@pytest.mark.parametrize("source", ["MANUAL", "CONVERSATION_SESSION"])
async def test_creation_records_source_and_correction_preserves_it(
    test_engine, source_data, source
):
    ids = source_data
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as db:
        event = await CareEventService(db, ids["tenant"]).create_candidate(
            elder_id=ids["elder"],
            actor_id=ids["worker"],
            trace_id=str(uuid4()),
            idempotency_key=str(uuid4()),
            request=CreateCareEventCandidateRequest(
                source_type=source,
                source_id=ids["session"] if source == "CONVERSATION_SESSION" else None,
                event_type="MEAL",
                structured_payload={"text": "Synthetic"},
                confidence_band="MEDIUM",
                extractor_version="synthetic",
            ),
        )
        assert event.source_type == source
        event_id = event.id
        await db.commit()
    async with _client(test_engine, ids) as client:
        response = await client.post(
            f"{_path(ids)}/{event_id}/review",
            headers=_headers(),
            json={
                "decision": "CORRECT",
                "reason_code": "SYNTHETIC",
                "expected_version": 1,
                "corrected_payload": {"text": "Synthetic corrected"},
                "corrected_event_type": "SLEEP",
            },
        )
        assert response.status_code == 200, response.text
        listed = await client.get(_path(ids), params={"source_type": source, "event_type": "SLEEP"})
        assert str(event_id) in [item["event_id"] for item in listed.json()["data"]["items"]]
    async with async_sessionmaker(test_engine)() as db:
        assert (await db.get(CareEvent, event_id)).source_type == source


async def test_summary_regeneration_does_not_duplicate_timeline(test_engine, source_data):
    ids = source_data
    async with _client(test_engine, ids) as client:
        before = await _pages(client, ids)
        async with async_sessionmaker(test_engine)() as db:
            service = SummaryService(db, ids["tenant"])
            for _ in range(2):
                await service.generate_from_verified_events(
                    elder_id=ids["elder"],
                    actor_id=ids["worker"],
                    summary_date=ANCHOR.date(),
                    trace_id=str(uuid4()),
                    idempotency_key=str(uuid4()),
                )
            await db.commit()
        assert await _pages(client, ids) == before


@pytest.mark.parametrize("source", ["manual", "VOICE", "", "MANUAL,UNKNOWN"])
async def test_unknown_filter_value_is_rejected(test_engine, source_data, source):
    async with _client(test_engine, source_data) as client:
        assert (
            await client.get(_path(source_data), params={"source_type": source})
        ).status_code == 422


@pytest.mark.parametrize(
    "scope", ["other_worker", "family", "other_tenant", "other_elder", "foreign_elder"]
)
async def test_source_filter_does_not_expand_authorization(test_engine, source_data, scope):
    ids = source_data
    target = {**ids, "elder": ids[scope]} if scope in {"other_elder", "foreign_elder"} else ids
    async with _client(
        test_engine,
        ids,
        actor=scope if scope in {"family", "other_worker"} else "worker",
        role="FAMILY_MEMBER" if scope == "family" else "HOME_CARE_WORKER",
        tenant="other_tenant" if scope == "other_tenant" else "tenant",
    ) as client:
        assert (
            await client.get(_path(target), params={"source_type": "MANUAL"})
        ).status_code == 404


async def test_pending_scope_and_expired_cursor_are_rechecked(test_engine, source_data):
    ids = source_data
    async with _client(test_engine, ids) as client:
        response = await client.get(_path(ids), params={"source_type": "MANUAL", "limit": 2})
        cursor = response.json()["data"]["next_cursor"]
        assert cursor
        async with async_sessionmaker(test_engine)() as db:
            assignment = await db.get(CareAssignment, ids["assignment"])
            assignment.service_scope = [
                scope for scope in assignment.service_scope if scope != "care_event:review"
            ]
            await db.commit()
        assert (
            await client.get(_path(ids), params={"source_type": "MANUAL", "status": "NEEDS_REVIEW"})
        ).status_code == 404
        assert (await client.get(_path(ids), params={"source_type": "MANUAL"})).status_code == 200
        async with async_sessionmaker(test_engine)() as db:
            assignment = await db.get(CareAssignment, ids["assignment"])
            assignment.service_end = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()
        assert (
            await client.get(_path(ids), params={"source_type": "MANUAL", "cursor": cursor})
        ).status_code == 404
