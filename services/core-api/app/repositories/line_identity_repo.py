"""Persistence operations for LINE account linking and webhook idempotency."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.line_identity import (
    ExternalIdentity,
    LineLinkChallenge,
    LineWebhookReceipt,
)

_WEBHOOK_MAX_ATTEMPTS = 3
_WEBHOOK_PROCESSING_STALE_AFTER = timedelta(minutes=2)


class LineIdentityRepository:
    """Store keyed external identities without persisting raw LINE IDs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_identity(self, identity: ExternalIdentity) -> None:
        self._session.add(identity)

    def add_challenge(self, challenge: LineLinkChallenge) -> None:
        self._session.add(challenge)

    async def get_active_identity_for_actor(
        self,
        actor_id: UUID,
        *,
        for_update: bool = False,
    ) -> ExternalIdentity | None:
        statement = select(ExternalIdentity).where(
            ExternalIdentity.provider == "LINE",
            ExternalIdentity.actor_id == actor_id,
            ExternalIdentity.status == "ACTIVE",
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def get_active_identity_by_subject(
        self,
        *,
        subject_digest: str,
        digest_key_version: int,
        for_update: bool = False,
    ) -> ExternalIdentity | None:
        statement = select(ExternalIdentity).where(
            ExternalIdentity.provider == "LINE",
            ExternalIdentity.external_subject_digest == subject_digest,
            ExternalIdentity.digest_key_version == digest_key_version,
            ExternalIdentity.status == "ACTIVE",
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def get_challenge_by_nonce(
        self,
        nonce_digest: str,
        *,
        for_update: bool = False,
    ) -> LineLinkChallenge | None:
        statement = select(LineLinkChallenge).where(LineLinkChallenge.nonce_digest == nonce_digest)
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def get_challenge_for_actor(
        self,
        *,
        challenge_id: UUID,
        actor_id: UUID,
        tenant_id: UUID,
        for_update: bool = False,
    ) -> LineLinkChallenge | None:
        statement = select(LineLinkChallenge).where(
            LineLinkChallenge.id == challenge_id,
            LineLinkChallenge.actor_id == actor_id,
            LineLinkChallenge.tenant_id == tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def expire_pending_challenges(
        self,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        now: datetime,
    ) -> None:
        await self._session.execute(
            update(LineLinkChallenge)
            .where(
                LineLinkChallenge.actor_id == actor_id,
                LineLinkChallenge.tenant_id == tenant_id,
                LineLinkChallenge.status == "PENDING",
            )
            .values(status="EXPIRED", expires_at=now, version=LineLinkChallenge.version + 1)
        )

    async def revoke_pending_challenges(
        self,
        *,
        actor_id: UUID,
        tenant_id: UUID,
        now: datetime,
    ) -> None:
        await self._session.execute(
            update(LineLinkChallenge)
            .where(
                LineLinkChallenge.actor_id == actor_id,
                LineLinkChallenge.tenant_id == tenant_id,
                LineLinkChallenge.status == "PENDING",
            )
            .values(
                status="REVOKED",
                revoked_at=now,
                version=LineLinkChallenge.version + 1,
            )
        )

    async def claim_webhook_event(
        self,
        *,
        webhook_event_id: str,
        event_type: str,
    ) -> Literal["CLAIMED", "DUPLICATE", "RETRY_LATER"]:
        statement = (
            insert(LineWebhookReceipt)
            .values(
                webhook_event_id=webhook_event_id,
                event_type=event_type,
                status="PROCESSING",
                attempt_count=1,
            )
            .on_conflict_do_nothing(index_elements=["webhook_event_id"])
            .returning(LineWebhookReceipt.id)
        )
        result = await self._session.execute(statement)
        if result.scalar_one_or_none() is not None:
            return "CLAIMED"

        receipt = await self._get_webhook_event_for_update(webhook_event_id)
        if receipt is None:
            return "RETRY_LATER"
        if receipt.status == "COMPLETED":
            return "DUPLICATE"

        now = datetime.now(UTC)
        retryable_failure = receipt.status == "FAILED"
        stale_processing = (
            receipt.status == "PROCESSING"
            and receipt.updated_at <= now - _WEBHOOK_PROCESSING_STALE_AFTER
        )
        if receipt.status == "PROCESSING" and not stale_processing:
            return "RETRY_LATER"
        if receipt.attempt_count >= _WEBHOOK_MAX_ATTEMPTS:
            return "DUPLICATE"
        if not retryable_failure and not stale_processing:
            return "DUPLICATE"

        receipt.status = "PROCESSING"
        receipt.event_type = event_type
        receipt.attempt_count += 1
        receipt.processed_at = None
        receipt.error_code = None
        await self._session.flush()
        return "CLAIMED"

    async def complete_webhook_event(self, webhook_event_id: str) -> None:
        receipt = await self._get_webhook_event_for_update(webhook_event_id)
        if receipt is not None:
            receipt.status = "COMPLETED"
            receipt.processed_at = datetime.now(UTC)
            receipt.error_code = None

    async def fail_webhook_event(
        self,
        webhook_event_id: str,
        *,
        error_code: str,
    ) -> None:
        receipt = await self._get_webhook_event_for_update(webhook_event_id)
        if receipt is not None:
            receipt.status = "FAILED"
            receipt.processed_at = datetime.now(UTC)
            receipt.error_code = error_code[:80]

    async def _get_webhook_event_for_update(
        self,
        webhook_event_id: str,
    ) -> LineWebhookReceipt | None:
        return await self._session.scalar(
            select(LineWebhookReceipt)
            .where(LineWebhookReceipt.webhook_event_id == webhook_event_id)
            .with_for_update()
        )
