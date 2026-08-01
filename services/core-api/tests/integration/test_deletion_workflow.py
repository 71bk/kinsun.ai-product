"""Deletion state machine, tombstone, tenant scope, and retry integration tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.exceptions import ConflictError, NotFoundError
from app.events.consumer import DomainEvent, IdempotentEventConsumer
from app.models.actor import Actor
from app.models.deletion import DeletionJobItem, DeletionRequest, DeletionTombstone
from app.models.elder import Elder
from app.models.memory import Memory, MemoryVersion
from app.models.outbox import OutboxEvent
from app.models.tenant import Tenant
from app.services.deletion_service import ApprovedDeletionPolicy, DeletionService


@dataclass(frozen=True)
class DeletionSeed:
    tenant_id: uuid.UUID
    other_tenant_id: uuid.UUID
    elder_id: uuid.UUID
    actor_id: uuid.UUID
    memory_id: uuid.UUID
    request_id: uuid.UUID


@pytest_asyncio.fixture(loop_scope="function")
async def deletion_seed(db_session) -> DeletionSeed:
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    elder_id = uuid.uuid4()
    memory_id = uuid.uuid4()
    request_id = uuid.uuid4()

    db_session.add_all(
        [
            Tenant(id=tenant_id, tenant_type="DEMO", name="Synthetic Deletion Tenant"),
            Tenant(
                id=other_tenant_id,
                tenant_type="DEMO",
                name="Synthetic Other Tenant",
            ),
            Actor(
                id=actor_id,
                actor_type="ELDER",
                display_name="Synthetic Elder Actor",
            ),
        ]
    )
    await db_session.flush()

    db_session.add(
        Elder(
            id=elder_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            display_name="Synthetic Deletion Elder",
            primary_care_setting="HOME_CARE",
        )
    )
    await db_session.flush()

    db_session.add_all(
        [
            Memory(
                id=memory_id,
                tenant_id=tenant_id,
                elder_id=elder_id,
                memory_type="PREFERENCE",
                status="ACTIVE",
                current_version=1,
                consent_version=1,
                confirmation_method="CAREGIVER_REVIEW",
                confirmation_evidence_ref="opaque:synthetic-confirmation",
            ),
            DeletionRequest(
                id=request_id,
                elder_id=elder_id,
                requested_by_actor_id=actor_id,
                scope=["MEMORY"],
                status="REQUESTED",
                reason_code="ELDER_REQUEST",
            ),
        ]
    )
    await db_session.flush()

    db_session.add_all(
        [
            MemoryVersion(
                memory_id=memory_id,
                version=1,
                content="synthetic preference that must be removed",
                source_event_ids=[],
                version_status="ACTIVE",
                created_by_actor_id=actor_id,
            ),
            DeletionJobItem(
                deletion_request_id=request_id,
                resource_type="MEMORY",
                system_of_record="AURORA",
                status="PENDING",
            ),
        ]
    )
    await db_session.flush()
    return DeletionSeed(
        tenant_id=tenant_id,
        other_tenant_id=other_tenant_id,
        elder_id=elder_id,
        actor_id=actor_id,
        memory_id=memory_id,
        request_id=request_id,
    )


def _approved_policy() -> ApprovedDeletionPolicy:
    return ApprovedDeletionPolicy(
        policy_version="privacy-deletion-v1",
        retention_basis="MINIMAL_REPLAY_PREVENTION_MARKER",
        legal_hold_status="CLEAR",
    )


async def test_memory_deletion_scrubs_content_and_writes_tombstone_and_outbox(
    db_session,
    deletion_seed: DeletionSeed,
) -> None:
    result = await DeletionService(db_session, deletion_seed.tenant_id).process_approved_request(
        elder_id=deletion_seed.elder_id,
        deletion_request_id=deletion_seed.request_id,
        policy=_approved_policy(),
        trace_id="trace-synthetic-deletion",
        idempotency_key="synthetic-deletion-1",
        actor_id=deletion_seed.actor_id,
    )

    assert result.status == "COMPLETED"
    assert result.completed_at is not None
    memory = await db_session.get(Memory, deletion_seed.memory_id)
    assert memory is not None
    assert memory.status == "DELETED"
    assert memory.confirmation_evidence_ref is None
    version = await db_session.scalar(
        select(MemoryVersion).where(MemoryVersion.memory_id == deletion_seed.memory_id)
    )
    assert version is not None
    assert version.content == ""
    assert version.source_event_ids == []
    assert version.version_status == "DELETED"

    tombstone = await db_session.scalar(
        select(DeletionTombstone).where(
            DeletionTombstone.tenant_id == deletion_seed.tenant_id,
            DeletionTombstone.resource_type == "MEMORY",
        )
    )
    assert tombstone is not None
    assert len(tombstone.subject_ref_hash) == 64
    assert len(tombstone.resource_id_hash) == 64
    assert str(deletion_seed.memory_id) not in tombstone.resource_id_hash

    event = await db_session.scalar(
        select(OutboxEvent).where(OutboxEvent.event_type == "deletion.completed.v1")
    )
    assert event is not None
    assert event.payload["status"] == "COMPLETED"
    assert "content" not in event.payload


async def test_legal_hold_gate_fails_without_side_effects(
    db_session,
    deletion_seed: DeletionSeed,
) -> None:
    service = DeletionService(db_session, deletion_seed.tenant_id)
    with pytest.raises(ConflictError):
        await service.process_approved_request(
            elder_id=deletion_seed.elder_id,
            deletion_request_id=deletion_seed.request_id,
            policy=ApprovedDeletionPolicy(
                policy_version="privacy-deletion-v1",
                retention_basis="LEGAL_HOLD_REVIEW",
                legal_hold_status="ACTIVE",
            ),
            trace_id="trace-blocked-deletion",
            idempotency_key="synthetic-deletion-blocked",
        )

    request = await db_session.get(DeletionRequest, deletion_seed.request_id)
    memory = await db_session.get(Memory, deletion_seed.memory_id)
    assert request is not None and request.status == "REQUESTED"
    assert memory is not None and memory.status == "ACTIVE"
    assert await db_session.scalar(select(func.count()).select_from(DeletionTombstone)) == 0


async def test_unconfigured_store_stays_partial_failed_and_retry_is_idempotent(
    db_session,
    deletion_seed: DeletionSeed,
) -> None:
    request = await db_session.get(DeletionRequest, deletion_seed.request_id)
    assert request is not None
    request.scope = ["MEMORY", "SEARCH_INDEX"]
    db_session.add(
        DeletionJobItem(
            deletion_request_id=deletion_seed.request_id,
            resource_type="SEARCH_INDEX",
            system_of_record="OPENSEARCH",
            status="PENDING",
        )
    )
    await db_session.flush()
    service = DeletionService(db_session, deletion_seed.tenant_id)

    first = await service.process_approved_request(
        elder_id=deletion_seed.elder_id,
        deletion_request_id=deletion_seed.request_id,
        policy=_approved_policy(),
        trace_id="trace-partial-deletion",
        idempotency_key="synthetic-partial-1",
    )
    assert first.status == "PARTIAL_FAILED"

    second = await service.process_approved_request(
        elder_id=deletion_seed.elder_id,
        deletion_request_id=deletion_seed.request_id,
        policy=_approved_policy(),
        trace_id="trace-partial-deletion-retry",
        idempotency_key="synthetic-partial-2",
    )
    assert second.status == "PARTIAL_FAILED"
    items = await service.list_items(
        elder_id=deletion_seed.elder_id,
        deletion_request_id=deletion_seed.request_id,
    )
    memory_item = next(item for item in items if item.resource_type == "MEMORY")
    search_item = next(item for item in items if item.resource_type == "SEARCH_INDEX")
    assert memory_item.status == "COMPLETED"
    assert memory_item.attempt_count == 1
    assert search_item.status == "FAILED"
    assert search_item.attempt_count == 2
    assert search_item.failure_code == "TARGET_NOT_CONFIGURED"
    assert await db_session.scalar(select(func.count()).select_from(DeletionTombstone)) == 1
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.event_type == "deletion.partial-failed.v1")
        )
        == 2
    )


async def test_cross_tenant_processing_is_not_discoverable(
    db_session,
    deletion_seed: DeletionSeed,
) -> None:
    with pytest.raises(NotFoundError):
        await DeletionService(
            db_session,
            deletion_seed.other_tenant_id,
        ).process_approved_request(
            elder_id=deletion_seed.elder_id,
            deletion_request_id=deletion_seed.request_id,
            policy=_approved_policy(),
            trace_id="trace-cross-tenant",
            idempotency_key="synthetic-cross-tenant",
        )

    request = await db_session.get(DeletionRequest, deletion_seed.request_id)
    assert request is not None and request.status == "REQUESTED"


async def test_consumer_suppresses_deleted_memory_replay(
    db_session,
    deletion_seed: DeletionSeed,
) -> None:
    await DeletionService(db_session, deletion_seed.tenant_id).process_approved_request(
        elder_id=deletion_seed.elder_id,
        deletion_request_id=deletion_seed.request_id,
        policy=_approved_policy(),
        trace_id="trace-replay-guard",
        idempotency_key="synthetic-replay-guard",
    )
    event = DomainEvent.model_validate(
        {
            "event_id": uuid.uuid4(),
            "event_type": "memory.confirmed.v1",
            "event_version": 1,
            "occurred_at": "2026-08-01T02:00:00Z",
            "tenant_id": deletion_seed.tenant_id,
            "elder_id": deletion_seed.elder_id,
            "actor_id": deletion_seed.actor_id,
            "purpose": None,
            "consent_version": None,
            "trace_id": "trace-stale-event",
            "correlation_id": "trace-stale-event",
            "causation_id": None,
            "idempotency_key": None,
            "classification": "CONFIDENTIAL",
            "aggregate": {
                "type": "memory",
                "id": deletion_seed.memory_id,
                "version": 1,
            },
            "payload": {"memory_id": str(deletion_seed.memory_id)},
        }
    )

    reason = await IdempotentEventConsumer(
        db_session,
        "synthetic_projection",
    )._suppression_reason(event)

    assert reason == "SUPPRESSED_DELETION_TOMBSTONE"
