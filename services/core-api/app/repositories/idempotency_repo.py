"""Tenant/actor-scoped, race-safe idempotency orchestration for write APIs."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationError
from app.models.idempotency import IdempotencyRecord

MAX_RESPONSE_SNAPSHOT_BYTES = 256 * 1024


@dataclass(frozen=True)
class IdempotencyResult:
    replayed: bool
    resource_type: str | None = None
    resource_id: UUID | None = None
    response_status: int | None = None
    response_body: dict | None = None


class IdempotencyRepository:
    """Atomically claim scoped keys and replay immutable response snapshots."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        actor_id: UUID | None,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._actor_id = actor_id

    @staticmethod
    def fingerprint(operation: str, payload: Any) -> str:
        canonical = json.dumps(
            {"operation": operation, "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def scoped_storage_key(
        tenant_id: UUID,
        actor_id: UUID | None,
        key: str,
    ) -> str:
        """Return a non-reversible physical key scoped to tenant and actor."""

        actor_scope = str(actor_id) if actor_id is not None else "SYSTEM"
        digest = hashlib.sha256(f"{tenant_id}:{actor_scope}:{key}".encode()).hexdigest()
        return f"v2:{digest}"

    def storage_key(self, key: str) -> str:
        return self.scoped_storage_key(self._tenant_id, self._actor_id, key)

    async def _find_existing(
        self,
        *,
        key: str,
        storage_key: str,
    ) -> IdempotencyRecord | None:
        """Lock a v2 row or a same-scope legacy raw-key row."""

        return await self._session.scalar(
            select(IdempotencyRecord)
            .where(
                or_(
                    IdempotencyRecord.idempotency_key == storage_key,
                    IdempotencyRecord.idempotency_key == key,
                ),
                IdempotencyRecord.tenant_id == self._tenant_id,
                IdempotencyRecord.actor_id == self._actor_id,
            )
            .order_by((IdempotencyRecord.idempotency_key == storage_key).desc())
            .with_for_update()
        )

    def _existing_result(
        self,
        *,
        record: IdempotencyRecord,
        request_fingerprint: str,
        now: datetime,
        ttl: timedelta,
    ) -> IdempotencyResult:
        if record.expires_at <= now:
            record.request_fingerprint = request_fingerprint
            record.resource_type = None
            record.resource_id = None
            record.status = "IN_PROGRESS"
            record.response_status = None
            record.response_body_hash = None
            record.response_body = None
            record.completed_at = None
            record.expires_at = now + ttl
            return IdempotencyResult(replayed=False)
        if record.request_fingerprint != request_fingerprint:
            raise ConflictError("Idempotency key was already used for a different request")
        if record.status == "COMPLETED":
            if record.response_body is not None:
                snapshot_hash = self.fingerprint("response", record.response_body)
                if snapshot_hash != record.response_body_hash:
                    raise ConflictError("Idempotency response snapshot failed integrity validation")
            return IdempotencyResult(
                replayed=True,
                resource_type=record.resource_type,
                resource_id=record.resource_id,
                response_status=record.response_status,
                response_body=deepcopy(record.response_body),
            )
        raise ConflictError("The idempotent request is already in progress")

    async def begin(
        self,
        *,
        key: str,
        operation: str,
        payload: Any,
        ttl: timedelta = timedelta(hours=24),
    ) -> IdempotencyResult:
        if not key or len(key) > 160:
            raise ValidationError(
                details=[
                    {
                        "field": "Idempotency-Key",
                        "reason": "A non-empty key of at most 160 characters is required",
                    }
                ]
            )

        now = datetime.now(UTC)
        request_fingerprint = self.fingerprint(operation, payload)
        storage_key = self.storage_key(key)
        existing = await self._find_existing(key=key, storage_key=storage_key)
        if existing is not None:
            return self._existing_result(
                record=existing,
                request_fingerprint=request_fingerprint,
                now=now,
                ttl=ttl,
            )

        inserted_key = await self._session.scalar(
            pg_insert(IdempotencyRecord)
            .values(
                idempotency_key=storage_key,
                actor_id=self._actor_id,
                tenant_id=self._tenant_id,
                request_fingerprint=request_fingerprint,
                status="IN_PROGRESS",
                key_format_version=2,
                expires_at=now + ttl,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(IdempotencyRecord.idempotency_key)
        )
        if inserted_key is not None:
            return IdempotencyResult(replayed=False)

        existing = await self._find_existing(key=key, storage_key=storage_key)
        if existing is None:
            raise ConflictError("Idempotency claim could not be resolved")
        return self._existing_result(
            record=existing,
            request_fingerprint=request_fingerprint,
            now=now,
            ttl=ttl,
        )

    async def complete(
        self,
        *,
        key: str,
        resource_type: str,
        resource_id: UUID,
        response_status: int,
        response_body: Any,
    ) -> None:
        record = await self._find_existing(key=key, storage_key=self.storage_key(key))
        if record is None or record.status != "IN_PROGRESS":
            raise ConflictError("Idempotency claim is not in progress")
        serialized = json.dumps(response_body, ensure_ascii=False, default=str)
        if len(serialized.encode("utf-8")) > MAX_RESPONSE_SNAPSHOT_BYTES:
            raise ConflictError("Idempotency response snapshot exceeds the storage limit")
        snapshot = json.loads(serialized)
        record.resource_type = resource_type
        record.resource_id = resource_id
        record.response_status = response_status
        record.response_body_hash = self.fingerprint("response", snapshot)
        record.response_body = snapshot
        record.status = "COMPLETED"
        record.completed_at = datetime.now(UTC)

    async def purge_expired(
        self,
        *,
        before: datetime | None = None,
    ) -> int:
        """Delete expired records for this tenant/actor scope."""

        result = await self._session.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.tenant_id == self._tenant_id,
                IdempotencyRecord.actor_id == self._actor_id,
                IdempotencyRecord.expires_at <= (before or datetime.now(UTC)),
            )
        )
        return int(result.rowcount or 0)
