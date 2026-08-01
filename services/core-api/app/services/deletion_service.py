"""Execute deletion work without bypassing retention or legal-hold policy."""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.deletion import hash_resource_ref, hash_subject_ref
from app.domain.state_machine import (
    require_deletion_item_transition,
    require_deletion_request_transition,
    require_memory_transition,
)
from app.events.outbox_writer import write_outbox_entry
from app.models.consent import ConsentGrant
from app.models.deletion import DeletionJobItem, DeletionRequest
from app.repositories.deletion_repo import DeletionRepository
from app.repositories.memory_repo import MemoryRepository

DEFAULT_SCOPE_BY_PURPOSE: dict[str, list[str]] = {
    "BASIC_VOICE": ["CONVERSATION_SESSION", "AUDIO_OBJECT", "CACHE"],
    "TRANSCRIPT_STORAGE": ["TRANSCRIPT", "AUDIO_OBJECT", "SEARCH_INDEX", "CACHE"],
    "CARE_EVENT_EXTRACTION": [
        "CARE_EVENT",
        "DAILY_SUMMARY",
        "FAMILY_REPORT",
        "GRAPH",
        "SEARCH_INDEX",
        "CACHE",
    ],
    "LONG_TERM_MEMORY": ["MEMORY", "GRAPH", "SEARCH_INDEX", "CACHE"],
    "COMPANION_SIGNAL_ANALYSIS": ["COMPANION_SIGNAL", "SEARCH_INDEX", "CACHE"],
    "PROACTIVE_COMPANION": ["PROACTIVE_TRIGGER", "CACHE"],
    "FAMILY_SHARING": ["FAMILY_REPORT", "NOTIFICATION", "SECURE_LINK", "CACHE"],
}

SYSTEM_BY_SCOPE = {
    "AUDIO_OBJECT": "S3",
    "GRAPH": "NEPTUNE",
    "SEARCH_INDEX": "OPENSEARCH",
    "CACHE": "CACHE",
}

ALLOWED_DELETION_SCOPES = frozenset(
    resource_type
    for default_scope in DEFAULT_SCOPE_BY_PURPOSE.values()
    for resource_type in default_scope
)


@dataclass(frozen=True)
class ApprovedDeletionPolicy:
    """Trusted policy result supplied by an internal deletion worker.

    This object is intentionally not an HTTP request schema. The caller must
    derive it from an approved server-side policy and legal-hold check.
    """

    policy_version: str
    retention_basis: str
    legal_hold_status: Literal["CLEAR", "ACTIVE", "NOT_EVALUATED", "RELEASED"]


class DeletionService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._repository = DeletionRepository(session, tenant_id)
        self._memories = MemoryRepository(session, tenant_id)

    async def get(
        self,
        *,
        elder_id: UUID,
        deletion_request_id: UUID,
    ) -> DeletionRequest | None:
        return await self._repository.get(
            elder_id=elder_id,
            deletion_request_id=deletion_request_id,
        )

    async def get_for_consent(
        self,
        *,
        elder_id: UUID,
        consent_id: UUID,
    ) -> DeletionRequest | None:
        return await self._repository.get_for_consent(
            elder_id=elder_id,
            consent_id=consent_id,
        )

    async def list_items(
        self,
        *,
        elder_id: UUID,
        deletion_request_id: UUID,
    ) -> list[DeletionJobItem]:
        return await self._repository.list_items(
            elder_id=elder_id,
            deletion_request_id=deletion_request_id,
        )

    async def create_for_revocation(
        self,
        *,
        consent: ConsentGrant,
        actor_id: UUID,
        requested_scope: list[str],
        reason_code: str,
        effective_at: datetime,
        trace_id: str,
        idempotency_key: str,
    ) -> DeletionRequest:
        existing = await self._repository.get_for_consent(
            elder_id=consent.elder_id,
            consent_id=consent.id,
        )
        if existing is not None:
            return existing

        scope = list(
            dict.fromkeys(requested_scope or DEFAULT_SCOPE_BY_PURPOSE.get(consent.purpose_code, []))
        )
        invalid_scope = sorted(set(scope) - ALLOWED_DELETION_SCOPES)
        if not scope or invalid_scope:
            raise ValidationError(
                details=[
                    {
                        "field": "revoke_scope",
                        "reason": "deletion scope is empty or contains an unsupported value",
                    }
                ]
            )

        deletion_request = DeletionRequest(
            elder_id=consent.elder_id,
            requested_by_actor_id=actor_id,
            consent_id=consent.id,
            scope=scope,
            status="REQUESTED",
            reason_code=reason_code,
            effective_at=effective_at,
        )
        self._repository.add_request(deletion_request)
        await self._session.flush()
        for resource_type in scope:
            self._repository.add_item(
                DeletionJobItem(
                    deletion_request_id=deletion_request.id,
                    resource_type=resource_type,
                    system_of_record=SYSTEM_BY_SCOPE.get(resource_type, "AURORA"),
                    status="PENDING",
                )
            )
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="deletion.requested.v1",
            aggregate_type="deletion_request",
            aggregate_id=deletion_request.id,
            aggregate_version=1,
            tenant_id=self._tenant_id,
            elder_id=consent.elder_id,
            actor_id=actor_id,
            purpose=consent.purpose_code,
            consent_version=consent.version,
            payload={
                "request_id": str(deletion_request.id),
                "scope": scope,
                "item_summary": {"pending": len(scope)},
                "reason_code": reason_code,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return deletion_request

    async def process_approved_request(
        self,
        *,
        elder_id: UUID,
        deletion_request_id: UUID,
        policy: ApprovedDeletionPolicy,
        trace_id: str,
        idempotency_key: str,
        actor_id: UUID | None = None,
    ) -> DeletionRequest:
        """Process all retryable items under an explicit trusted policy decision."""
        self._validate_policy(policy)
        deletion_request = await self._repository.get(
            elder_id=elder_id,
            deletion_request_id=deletion_request_id,
            for_update=True,
        )
        if deletion_request is None:
            raise NotFoundError("Resource not found")
        if deletion_request.status == "COMPLETED":
            return deletion_request
        if deletion_request.status == "CANCELLED":
            raise ConflictError("A cancelled deletion request cannot be processed")

        if deletion_request.status in {"REQUESTED", "PARTIAL_FAILED"}:
            require_deletion_request_transition(deletion_request.status, "IN_PROGRESS")
            deletion_request.status = "IN_PROGRESS"
        elif deletion_request.status != "IN_PROGRESS":
            raise ConflictError("Deletion request is not processable")

        deletion_request.policy_version = policy.policy_version
        deletion_request.legal_hold_status = policy.legal_hold_status
        deletion_request.retention_basis = policy.retention_basis
        deletion_request.completed_at = None

        items = await self._repository.list_items(
            elder_id=elder_id,
            deletion_request_id=deletion_request_id,
            for_update=True,
        )
        if not items:
            raise ConflictError("Deletion request has no work items")

        for item in items:
            if item.status in {"COMPLETED", "SKIPPED"}:
                continue
            self._start_item(item)
            await self._session.flush()
            if item.system_of_record == "AURORA" and item.resource_type == "MEMORY":
                deleted_count = await self._delete_memories(
                    deletion_request=deletion_request,
                    policy=policy,
                )
                self._complete_item(
                    item,
                    verification_code=(
                        "CONTENT_REMOVED_AND_MARKED" if deleted_count else "NO_MATCHING_RESOURCE"
                    ),
                )
            else:
                self._fail_item(item, failure_code="TARGET_NOT_CONFIGURED")

        self._reconcile_request(deletion_request, items)
        await self._session.flush()
        await self._write_result_event(
            deletion_request=deletion_request,
            items=items,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return deletion_request

    @staticmethod
    def _validate_policy(policy: ApprovedDeletionPolicy) -> None:
        if not policy.policy_version.strip() or len(policy.policy_version) > 64:
            raise ValidationError(
                details=[{"field": "policy_version", "reason": "approved policy is required"}]
            )
        if not policy.retention_basis.strip() or len(policy.retention_basis) > 120:
            raise ValidationError(
                details=[{"field": "retention_basis", "reason": "retention basis is required"}]
            )
        if policy.legal_hold_status != "CLEAR":
            raise ConflictError("Deletion is blocked until legal-hold status is CLEAR")

    @staticmethod
    def _start_item(item: DeletionJobItem) -> None:
        require_deletion_item_transition(item.status, "PROCESSING")
        item.status = "PROCESSING"
        item.attempt_count += 1
        item.started_at = datetime.now(UTC)
        item.completed_at = None
        item.failure_code = None
        item.verification_code = None
        item.last_error = None

    @staticmethod
    def _complete_item(item: DeletionJobItem, *, verification_code: str) -> None:
        require_deletion_item_transition(item.status, "COMPLETED")
        item.status = "COMPLETED"
        item.verification_code = verification_code
        item.completed_at = datetime.now(UTC)

    @staticmethod
    def _fail_item(item: DeletionJobItem, *, failure_code: str) -> None:
        require_deletion_item_transition(item.status, "FAILED")
        item.status = "FAILED"
        item.failure_code = failure_code
        item.last_error = failure_code
        item.completed_at = None

    @staticmethod
    def _reconcile_request(
        deletion_request: DeletionRequest,
        items: list[DeletionJobItem],
    ) -> None:
        statuses = {item.status for item in items}
        if statuses <= {"COMPLETED", "SKIPPED"}:
            target = "COMPLETED"
        elif "FAILED" in statuses and not statuses.intersection({"PENDING", "PROCESSING"}):
            target = "PARTIAL_FAILED"
        else:
            return
        require_deletion_request_transition(deletion_request.status, target)
        deletion_request.status = target
        deletion_request.completed_at = datetime.now(UTC) if target == "COMPLETED" else None

    async def _delete_memories(
        self,
        *,
        deletion_request: DeletionRequest,
        policy: ApprovedDeletionPolicy,
    ) -> int:
        memories = await self._memories.list_for_deletion(elder_id=deletion_request.elder_id)
        versions = await self._memories.list_versions_for_deletion(
            memory_ids=[memory.id for memory in memories]
        )
        now = datetime.now(UTC)
        for version in versions:
            version.content = ""
            version.source_event_ids = []
            version.version_status = "DELETED"
            version.valid_to = now
        subject_ref_hash = hash_subject_ref(self._tenant_id, deletion_request.elder_id)
        for memory in memories:
            if memory.status != "DELETED":
                require_memory_transition(memory.status, "DELETED")
            memory.status = "DELETED"
            memory.deleted_at = now
            memory.deactivated_at = now
            memory.confirmation_method = None
            memory.confirmation_session_id = None
            memory.confirmation_evidence_ref = None
            await self._repository.add_tombstone(
                elder_id=deletion_request.elder_id,
                deletion_request_id=deletion_request.id,
                subject_ref_hash=subject_ref_hash,
                resource_type="MEMORY",
                resource_id_hash=hash_resource_ref("MEMORY", memory.id),
                deleted_at=now,
                policy_version=policy.policy_version,
                reason_code=deletion_request.reason_code or "CONSENT_REVOKED",
                retention_basis=policy.retention_basis,
            )
        return len(memories)

    async def _write_result_event(
        self,
        *,
        deletion_request: DeletionRequest,
        items: list[DeletionJobItem],
        actor_id: UUID | None,
        trace_id: str,
        idempotency_key: str,
    ) -> None:
        if deletion_request.status not in {"COMPLETED", "PARTIAL_FAILED"}:
            return
        attempt = max(item.attempt_count for item in items)
        event_type = (
            "deletion.completed.v1"
            if deletion_request.status == "COMPLETED"
            else "deletion.partial-failed.v1"
        )
        event_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"https://kinsun.ai/deletions/{deletion_request.id}/{event_type}/{attempt}",
        )
        item_summary = Counter(item.status.lower() for item in items)
        await write_outbox_entry(
            self._session,
            event_id=event_id,
            event_type=event_type,
            aggregate_type="deletion_request",
            aggregate_id=deletion_request.id,
            aggregate_version=max(2, attempt + 1),
            tenant_id=self._tenant_id,
            elder_id=deletion_request.elder_id,
            actor_id=actor_id,
            payload={
                "request_id": str(deletion_request.id),
                "status": deletion_request.status,
                "item_summary": dict(item_summary),
                "policy_version": deletion_request.policy_version,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=(
                f"{idempotency_key[:96]}:deletion:{deletion_request.status}:{attempt}"
            ),
        )
