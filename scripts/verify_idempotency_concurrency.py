"""Verify first-use idempotency serialization against an opted-in Demo database."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_API_ROOT = REPO_ROOT / "services" / "core-api"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(CORE_API_ROOT))

from app.models.actor import Actor  # noqa: E402
from app.models.idempotency import IdempotencyRecord  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.repositories.idempotency_repo import IdempotencyRepository  # noqa: E402
from scripts.seed_demo import MANIFEST_PATH, _database_url  # noqa: E402


async def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    tenant_id = UUID(manifest["tenants"]["daycare"])
    actor_id = UUID(manifest["actors"]["daycare_worker"])
    resource_id = uuid4()
    client_key = f"qa-idempotency-concurrency:{uuid4()}"
    engine = create_async_engine(_database_url(), hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    storage_key = IdempotencyRepository.scoped_storage_key(
        tenant_id,
        actor_id,
        client_key,
    )
    inserted = asyncio.Event()
    finish_first = asyncio.Event()
    execution_count = 0
    tasks: list[asyncio.Task] = []

    async def first_request() -> None:
        nonlocal execution_count
        async with factory() as session, session.begin():
            claim = await IdempotencyRepository(session, tenant_id, actor_id).begin(
                key=client_key,
                operation="qa_concurrent_claim",
                payload={"value": 1},
            )
            if claim.replayed:
                raise RuntimeError("The first request unexpectedly replayed")
            execution_count += 1
            inserted.set()
            await finish_first.wait()
            await IdempotencyRepository(session, tenant_id, actor_id).complete(
                key=client_key,
                resource_type="qa_resource",
                resource_id=resource_id,
                response_status=201,
                response_body={"resource_id": str(resource_id), "version": 1},
            )

    async def concurrent_request():
        await inserted.wait()
        async with factory() as session, session.begin():
            return await IdempotencyRepository(session, tenant_id, actor_id).begin(
                key=client_key,
                operation="qa_concurrent_claim",
                payload={"value": 1},
            )

    try:
        async with factory() as session:
            tenant = await session.get(Tenant, tenant_id)
            actor = await session.get(Actor, actor_id)
            if tenant is None or tenant.tenant_type != "DEMO" or actor is None:
                raise RuntimeError(
                    "Verifier requires the fixed synthetic Demo tenant and actor"
                )

        first_task = asyncio.create_task(first_request())
        tasks.append(first_task)
        await asyncio.wait_for(inserted.wait(), timeout=15)
        second_task = asyncio.create_task(concurrent_request())
        tasks.append(second_task)
        await asyncio.sleep(0.25)
        finish_first.set()
        _, replay = await asyncio.wait_for(
            asyncio.gather(first_task, second_task),
            timeout=30,
        )
        expected = {"resource_id": str(resource_id), "version": 1}
        if (
            execution_count != 1
            or not replay.replayed
            or replay.response_body != expected
        ):
            raise RuntimeError("Concurrent idempotency verification failed")
        print(
            json.dumps(
                {
                    "ok": True,
                    "execution_count": execution_count,
                    "second_request_replayed": replay.replayed,
                    "snapshot_matched": replay.response_body == expected,
                }
            )
        )
    finally:
        finish_first.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with factory() as session, session.begin():
            await session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.idempotency_key == storage_key,
                    IdempotencyRecord.tenant_id == tenant_id,
                    IdempotencyRecord.actor_id == actor_id,
                )
            )
            remaining = await session.scalar(
                select(IdempotencyRecord.idempotency_key).where(
                    IdempotencyRecord.idempotency_key == storage_key
                )
            )
            if remaining is not None:
                raise RuntimeError("Verifier cleanup failed")
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
