"""Consent API with live authorization and purpose separation."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.exceptions import NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.middleware.auth import ActorContext
from app.models.policy import PolicyRegistry
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.consent import (
    ConsentListResponse,
    ConsentResponse,
    CreateConsentRequest,
    RevokeConsentRequest,
)
from app.services.authorization_service import authorize_elder
from app.services.consent_service import CAPABILITIES, ConsentService
from app.services.deletion_service import DeletionService

router = APIRouter(prefix="/api/v1", tags=["consents"])


async def _response_for(
    session: AsyncSession,
    consent,
    deletion_request_id: UUID | None = None,
) -> ConsentResponse:
    policy_version = await session.scalar(
        select(PolicyRegistry.version).where(PolicyRegistry.id == consent.policy_id)
    )
    return ConsentResponse(
        consent_id=consent.id,
        purpose_code=consent.purpose_code,
        consent_version=consent.version,
        status=consent.status,
        scope=consent.scope,
        policy_version=policy_version or "unknown",
        effective_at=consent.effective_at,
        expires_at=consent.expires_at,
        revoked_at=consent.revoked_at,
        affected_capabilities=CAPABILITIES.get(consent.purpose_code, []),
        deletion_request_id=deletion_request_id,
    )


@router.get("/elders/{elder_id}/consents")
async def list_consents(
    elder_id: UUID = Path(...),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "consent:read")
    consents = await ConsentService(session, actor_context.tenant_id).list_for_elder(elder_id)
    items = [await _response_for(session, item) for item in consents]
    return success(ConsentListResponse(items=items).model_dump(mode="json"))


@router.post("/elders/{elder_id}/consents", status_code=status.HTTP_201_CREATED)
async def create_consents(
    request: CreateConsentRequest,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "consent:write")
    idem = IdempotencyRepository(
        session,
        actor_context.tenant_id,
        actor_context.actor_id,
    )
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_consents",
        payload={"elder_id": elder_id, **request.model_dump(mode="json")},
    )
    service = ConsentService(session, actor_context.tenant_id)
    if replay.replayed:
        all_consents = await service.list_for_elder(elder_id)
        requested = {purpose.value for purpose in request.purposes}
        latest: dict[str, object] = {}
        for consent in all_consents:
            if consent.purpose_code in requested and consent.purpose_code not in latest:
                latest[consent.purpose_code] = consent
        created = list(latest.values())
    else:
        created = await service.create_grants(
            elder_id=elder_id,
            actor_id=actor_context.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="consent_batch",
            resource_id=created[0].id,
            response_status=status.HTTP_201_CREATED,
            response_body={"consent_ids": [str(item.id) for item in created]},
        )

    items = [await _response_for(session, item) for item in created]
    return success(ConsentListResponse(items=items).model_dump(mode="json"))


@router.post("/elders/{elder_id}/consents/{consent_id}/revoke")
async def revoke_consent(
    request: RevokeConsentRequest,
    elder_id: UUID = Path(...),
    consent_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "consent:revoke")
    idem = IdempotencyRepository(
        session,
        actor_context.tenant_id,
        actor_context.actor_id,
    )
    replay = await idem.begin(
        key=idempotency_key,
        operation="revoke_consent",
        payload={
            "elder_id": elder_id,
            "consent_id": consent_id,
            **request.model_dump(mode="json"),
        },
    )
    service = ConsentService(session, actor_context.tenant_id)
    deletion_request_id = None
    if replay.replayed:
        consent = await service.get_by_id(elder_id, consent_id)
        if consent is None:
            raise NotFoundError("Resource not found")
    else:
        consent, deletion_request_id = await service.revoke(
            elder_id=elder_id,
            consent_id=consent_id,
            actor_id=actor_context.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="consent_grant",
            resource_id=consent.id,
            response_status=200,
            response_body={"consent_id": str(consent.id), "status": consent.status},
        )
    if replay.replayed and request.request_deletion:
        deletion_request = await DeletionService(
            session,
            actor_context.tenant_id,
        ).get_for_consent(
            elder_id=elder_id,
            consent_id=consent_id,
        )
        deletion_request_id = deletion_request.id if deletion_request else None
    return success(
        (
            await _response_for(
                session,
                consent,
                deletion_request_id=deletion_request_id,
            )
        ).model_dump(mode="json")
    )
