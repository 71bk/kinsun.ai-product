"""Private BFF-to-Core Google OIDC handoff and onboarding endpoints."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.bootstrap.dependencies import (
    get_family_invitation_token_codec,
    get_google_identity_codec,
    get_google_oidc_handoff_authenticator,
)
from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.core.oidc import GoogleTokenVerifier
from app.db.session import get_db_session
from app.middleware.auth import get_google_token_verifier
from app.schemas.google_oidc_handoff import (
    AuthenticatedGoogleOidcHandoffResponse,
    CompletedGoogleOnboardingResponse,
    CompleteGoogleOnboardingRequest,
    GoogleOidcHandoffRequest,
    PendingGoogleOidcHandoffResponse,
)
from app.services.app_session_service import AppSessionPolicy, AppSessionService
from app.services.family_invitation_service import FamilyInvitationService
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec
from app.services.google_identity_codec import GoogleIdentityCodec
from app.services.google_oidc_handoff_auth import GoogleOidcHandoffAuthenticator
from app.services.google_oidc_handoff_service import (
    AuthenticatedGoogleHandoff,
    GoogleOidcHandoffService,
    PendingIdentityPolicy,
)
from app.services.pending_google_onboarding_service import PendingGoogleOnboardingService

router = APIRouter(prefix="/api/v1/internal/auth/google", tags=["internal-auth"])


def require_google_oidc_bff(
    request: Request,
    authenticator: GoogleOidcHandoffAuthenticator = Depends(get_google_oidc_handoff_authenticator),
) -> None:
    authenticator.authenticate(request.headers.getlist("x-kinsun-bff-authorization"))


@router.post("/handoff", status_code=status.HTTP_200_OK)
async def handoff_google_oidc(
    request: GoogleOidcHandoffRequest,
    response: Response,
    _: None = Depends(require_google_oidc_bff),
    verifier: GoogleTokenVerifier = Depends(get_google_token_verifier),
    session: AsyncSession = Depends(get_db_session),
    identity_codec: GoogleIdentityCodec = Depends(get_google_identity_codec),
) -> dict:
    """Exchange a verified Google identity for one Core-owned credential."""
    settings = get_settings()
    service = GoogleOidcHandoffService(
        session,
        verifier=verifier,
        identity_codec=identity_codec,
        app_session_service=AppSessionService(
            session,
            AppSessionPolicy.from_settings(settings),
        ),
        pending_policy=PendingIdentityPolicy(
            timedelta(seconds=settings.google_pending_identity_ttl_seconds)
        ),
        allow_new_accounts=not settings.kinsun_native_auth_enabled,
    )
    result = await service.handoff(
        id_token=request.id_token,
        expected_nonce=request.expected_nonce,
        intent=request.intent,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    if isinstance(result, AuthenticatedGoogleHandoff):
        payload = AuthenticatedGoogleOidcHandoffResponse(
            session_token=result.session.token,
            idle_expires_at=result.session.idle_expires_at,
            absolute_expires_at=result.session.absolute_expires_at,
        )
    else:
        payload = PendingGoogleOidcHandoffResponse(
            pending_token=result.token,
            expires_at=result.expires_at,
        )
    return success(payload.model_dump(mode="json"))


@router.post("/onboarding", status_code=status.HTTP_200_OK)
async def complete_google_onboarding(
    request: CompleteGoogleOnboardingRequest,
    response: Response,
    _: None = Depends(require_google_oidc_bff),
    session: AsyncSession = Depends(get_db_session),
    invitation_codec: FamilyInvitationTokenCodec = Depends(get_family_invitation_token_codec),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    """Atomically consume a pending identity and issue its first App Session."""
    settings = get_settings()
    if idempotency_key is not None:
        operation_key = idempotency_key.strip()
        if not operation_key or len(operation_key) > 160:
            raise ValidationError(
                details=[
                    {
                        "field": "Idempotency-Key",
                        "reason": "A non-empty key of at most 160 characters is required",
                    }
                ]
            )
    else:
        operation_key = hashlib.sha256(
            f"google-onboarding:{request.pending_token}".encode("ascii")
        ).hexdigest()
    result = await PendingGoogleOnboardingService(
        session,
        app_session_service=AppSessionService(
            session,
            AppSessionPolicy.from_settings(settings),
        ),
        family_invitation_service=FamilyInvitationService(session, invitation_codec),
    ).complete(
        pending_token=request.pending_token,
        invitation_code=request.invitation_code,
        display_name=request.display_name,
        trace_id=get_correlation_id(),
        idempotency_key=operation_key,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    payload = CompletedGoogleOnboardingResponse(
        status=result.status,
        intent=result.intent,
        actor_id=result.actor_id,
        tenant_id=result.tenant_id,
        elder_id=result.elder_id,
        session_token=result.session.token,
        idle_expires_at=result.session.idle_expires_at,
        absolute_expires_at=result.session.absolute_expires_at,
    )
    return success(payload.model_dump(mode="json"))
