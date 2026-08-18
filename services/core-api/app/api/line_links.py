"""Authenticated ELDER/FAMILY LINE link management endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.bootstrap.dependencies import (
    get_line_identity_codec,
    get_line_subject_cipher,
)
from app.core.auth import ActorContext
from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceUnavailableError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.schemas.line_identity import CreateLineLinkChallengeRequest
from app.services.line_account_link_service import LineAccountLinkService
from app.services.line_identity_codec import LineIdentityCodec

router = APIRouter(prefix="/api/v1/me", tags=["line-account-linking"])


def _service(
    session: AsyncSession,
    codec: LineIdentityCodec,
    settings: Settings,
) -> LineAccountLinkService:
    if not settings.line_account_link_enabled:
        raise ServiceUnavailableError("LINE account linking is unavailable")
    return LineAccountLinkService(
        session,
        codec,
        challenge_ttl_seconds=settings.line_link_challenge_ttl_seconds,
        challenge_max_attempts=settings.line_link_challenge_max_attempts,
        frontend_base_url=settings.line_account_link_base_url,
        subject_cipher=(
            get_line_subject_cipher() if settings.line_daily_notification_enabled else None
        ),
    )


@router.get("/line-link")
async def get_line_link_status(
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    codec: LineIdentityCodec = Depends(get_line_identity_codec),
    settings: Settings = Depends(get_settings),
) -> dict:
    result = await _service(session, codec, settings).get_status(actor)
    return success(result.model_dump(mode="json"))


@router.post("/line-link-challenges", status_code=status.HTTP_201_CREATED)
async def create_line_link_challenge(
    request: CreateLineLinkChallengeRequest,
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    codec: LineIdentityCodec = Depends(get_line_identity_codec),
    settings: Settings = Depends(get_settings),
) -> dict:
    result = await _service(session, codec, settings).create_challenge(
        actor=actor,
        link_token=request.link_token,
    )
    return success(result.model_dump(mode="json"))


@router.get("/line-link-challenges/{challenge_id}")
async def get_line_link_challenge_status(
    challenge_id: UUID = Path(...),
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    codec: LineIdentityCodec = Depends(get_line_identity_codec),
    settings: Settings = Depends(get_settings),
) -> dict:
    result = await _service(session, codec, settings).get_challenge_status(
        actor=actor,
        challenge_id=challenge_id,
    )
    return success(result.model_dump(mode="json"))


@router.delete("/line-link")
async def unlink_line_account(
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
    codec: LineIdentityCodec = Depends(get_line_identity_codec),
    settings: Settings = Depends(get_settings),
) -> dict:
    result = await _service(session, codec, settings).unlink(
        actor=actor,
        trace_id=get_correlation_id(),
    )
    return success(result.model_dump(mode="json"))
