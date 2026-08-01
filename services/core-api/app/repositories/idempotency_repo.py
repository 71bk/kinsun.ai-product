"""Hash-only idempotency orchestration for write APIs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationError
from app.models.idempotency import IdempotencyRecord


@dataclass(frozen=True)
class IdempotencyResult:
    replayed: bool
    resource_type: str | None = None
    resource_id: UUID | None = None


class IdempotencyRepository:
    """Detect same-key/different-request conflicts without storing responses."""

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

        request_fingerprint = self.fingerprint(operation, payload)
        result = await self._session.execute(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.idempotency_key == key)
            .with_for_update()
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            if (
                existing.actor_id != self._actor_id
                or existing.tenant_id != self._tenant_id
                or existing.request_fingerprint != request_fingerprint
            ):
                raise ConflictError("Idempotency key was already used for a different request")
            if existing.status == "COMPLETED":
                return IdempotencyResult(
                    replayed=True,
                    resource_type=existing.resource_type,
                    resource_id=existing.resource_id,
                )
            raise ConflictError("The idempotent request is already in progress")

        self._session.add(
            IdempotencyRecord(
                idempotency_key=key,
                actor_id=self._actor_id,
                tenant_id=self._tenant_id,
                request_fingerprint=request_fingerprint,
                status="IN_PROGRESS",
                expires_at=datetime.now(UTC) + ttl,
            )
        )
        await self._session.flush()
        return IdempotencyResult(replayed=False)

    async def complete(
        self,
        *,
        key: str,
        resource_type: str,
        resource_id: UUID,
        response_status: int,
        response_body: Any,
    ) -> None:
        result = await self._session.execute(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.idempotency_key == key)
            .with_for_update()
        )
        record = result.scalar_one()
        record.resource_type = resource_type
        record.resource_id = resource_id
        record.response_status = response_status
        record.response_body_hash = self.fingerprint("response", response_body)
        record.status = "COMPLETED"
