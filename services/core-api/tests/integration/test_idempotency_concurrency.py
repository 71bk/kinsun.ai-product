"""PostgreSQL proof that first-use idempotency claims serialize safely."""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.idempotency_repo import IdempotencyRepository

TENANT_ID = UUID("a2000000-0000-4000-8000-000000000001")
ACTOR_ID = UUID("a2000000-0000-4000-8000-000000000002")
RESOURCE_ID = UUID("a2000000-0000-4000-8000-000000000003")


@pytest.mark.asyncio
async def test_same_first_use_key_executes_once_and_replays_to_concurrent_caller(
    committed_session: AsyncSession,
    test_engine,
) -> None:
    await committed_session.execute(
        text(
            """
            INSERT INTO eldercare_ai.tenant
                (tenant_id, tenant_type, name, status, timezone)
            VALUES (:tenant_id, 'DEMO', 'Idempotency concurrency tenant', 'ACTIVE', 'UTC');
            INSERT INTO eldercare_ai.actor
                (actor_id, actor_type, display_name, status)
            VALUES (:actor_id, 'SYSTEM_SERVICE', 'Idempotency concurrency actor', 'ACTIVE');
            """
        ),
        {"tenant_id": TENANT_ID, "actor_id": ACTOR_ID},
    )
    await committed_session.commit()

    inserted = asyncio.Event()
    finish_first = asyncio.Event()
    execution_count = 0
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def first_request():
        nonlocal execution_count
        async with factory() as session, session.begin():
            repository = IdempotencyRepository(session, TENANT_ID, ACTOR_ID)
            claim = await repository.begin(
                key="concurrent-first-use",
                operation="create_resource",
                payload={"value": 1},
            )
            assert claim.replayed is False
            execution_count += 1
            inserted.set()
            await finish_first.wait()
            await repository.complete(
                key="concurrent-first-use",
                resource_type="synthetic_resource",
                resource_id=RESOURCE_ID,
                response_status=201,
                response_body={"resource_id": str(RESOURCE_ID), "version": 1},
            )

    async def concurrent_request():
        await inserted.wait()
        async with factory() as session, session.begin():
            return await IdempotencyRepository(session, TENANT_ID, ACTOR_ID).begin(
                key="concurrent-first-use",
                operation="create_resource",
                payload={"value": 1},
            )

    first_task = asyncio.create_task(first_request())
    second_task = asyncio.create_task(concurrent_request())
    await inserted.wait()
    await asyncio.sleep(0.05)
    finish_first.set()
    await first_task
    replay = await second_task

    assert execution_count == 1
    assert replay.replayed is True
    assert replay.response_status == 201
    assert replay.response_body == {"resource_id": str(RESOURCE_ID), "version": 1}
