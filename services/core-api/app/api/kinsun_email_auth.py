"""Private BFF-to-Core Kinsun email authentication endpoints."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.config import get_settings
from app.db.session import get_db_session
from app.schemas.kinsun_email_auth import (
    CompletedKinsunEmailAuthResponse,
    CompleteKinsunEmailAuthRequest,
    StartedKinsunEmailAuthResponse,
    StartKinsunEmailAuthRequest,
)
from app.services.app_session_service import AppSessionPolicy, AppSessionService
from app.services.family_invitation_service import FamilyInvitationService
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec
from app.services.kinsun_auth_handoff import KinsunAuthHandoffAuthenticator
from app.services.kinsun_email_auth_service import (
    CompletedKinsunEmailAuthentication,
    KinsunEmailAuthService,
    KinsunEmailChallengePolicy,
)
from app.services.kinsun_identity_codec import (
    KinsunEmailChallengeCodec,
    KinsunIdentityCodec,
)
from app.services.service_dependencies import (
    get_family_invitation_token_codec,
    get_kinsun_auth_handoff_authenticator,
    get_kinsun_email_challenge_codec,
    get_kinsun_identity_codec,
)

router = APIRouter(prefix="/api/v1/internal/auth/kinsun/email", tags=["internal-auth"])


def require_kinsun_auth_bff(
    request: Request,
    authenticator: KinsunAuthHandoffAuthenticator = Depends(
        get_kinsun_auth_handoff_authenticator
    ),
) -> None:
    authenticator.authenticate(request.headers.getlist("x-kinsun-bff-authorization"))


def _service(
    session: AsyncSession,
    *,
    identity_codec: KinsunIdentityCodec,
    challenge_codec: KinsunEmailChallengeCodec,
    invitation_codec: FamilyInvitationTokenCodec,
) -> KinsunEmailAuthService:
    settings = get_settings()
    return KinsunEmailAuthService(
        session,
        identity_codec=identity_codec,
        challenge_codec=challenge_codec,
        app_session_service=AppSessionService(
            session,
            AppSessionPolicy.from_settings(settings),
        ),
        family_invitation_service=FamilyInvitationService(session, invitation_codec),
        policy=KinsunEmailChallengePolicy(
            ttl=timedelta(seconds=settings.kinsun_email_challenge_ttl_seconds),
            max_attempts=settings.kinsun_email_challenge_max_attempts,
        ),
        verification_code=settings.kinsun_synthetic_email_code_secret,
    )


@router.post("/start", status_code=status.HTTP_200_OK)
async def start_kinsun_email_auth(
    request: StartKinsunEmailAuthRequest,
    response: Response,
    _: None = Depends(require_kinsun_auth_bff),
    session: AsyncSession = Depends(get_db_session),
    identity_codec: KinsunIdentityCodec = Depends(get_kinsun_identity_codec),
    challenge_codec: KinsunEmailChallengeCodec = Depends(
        get_kinsun_email_challenge_codec
    ),
    invitation_codec: FamilyInvitationTokenCodec = Depends(
        get_family_invitation_token_codec
    ),
) -> dict:
    """Create a uniform challenge without revealing whether an account exists."""
    result = await _service(
        session,
        identity_codec=identity_codec,
        challenge_codec=challenge_codec,
        invitation_codec=invitation_codec,
    ).start(
        email=request.email,
        intent=request.intent,
        display_name=request.display_name,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    payload = StartedKinsunEmailAuthResponse(
        challenge_token=result.token,
        expires_at=result.expires_at,
    )
    return success(payload.model_dump(mode="json"))


@router.post("/complete", status_code=status.HTTP_200_OK, response_model=None)
async def complete_kinsun_email_auth(
    request: CompleteKinsunEmailAuthRequest,
    _: None = Depends(require_kinsun_auth_bff),
    session: AsyncSession = Depends(get_db_session),
    identity_codec: KinsunIdentityCodec = Depends(get_kinsun_identity_codec),
    challenge_codec: KinsunEmailChallengeCodec = Depends(
        get_kinsun_email_challenge_codec
    ),
    invitation_codec: FamilyInvitationTokenCodec = Depends(
        get_family_invitation_token_codec
    ),
) -> dict | JSONResponse:
    """Consume one code and issue a Core App Session on success."""
    operation_key = hashlib.sha256(
        f"kinsun-email:{request.challenge_token}".encode("ascii")
    ).hexdigest()
    result = await _service(
        session,
        identity_codec=identity_codec,
        challenge_codec=challenge_codec,
        invitation_codec=invitation_codec,
    ).complete(
        challenge_token=request.challenge_token,
        verification_code=request.verification_code,
        invitation_code=request.invitation_code,
        trace_id=get_correlation_id(),
        idempotency_key=operation_key,
    )
    if not isinstance(result, CompletedKinsunEmailAuthentication):
        correlation_id = get_correlation_id()
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            content={
                "error": {
                    "code": "authentication_required",
                    "message": "Authentication required.",
                    "correlation_id": correlation_id,
                    "reason_code": "AUTHENTICATION_FAILED",
                    "retryable": False,
                    "details": None,
                },
                "meta": {
                    "correlation_id": correlation_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "schema_version": "1.0",
                },
            },
        )

    payload = CompletedKinsunEmailAuthResponse(
        session_token=result.session.token,
        idle_expires_at=result.session.idle_expires_at,
        absolute_expires_at=result.session.absolute_expires_at,
    )
    return success(payload.model_dump(mode="json"))
