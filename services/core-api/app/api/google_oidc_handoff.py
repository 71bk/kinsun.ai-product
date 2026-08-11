"""Unbound private BFF-to-Core Google OIDC handoff endpoint.

The router is intentionally not included by ``app.main`` until the browser
callback, cookie adapter, and onboarding consumption phases are complete.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth.google_oidc import GoogleTokenVerifier
from app.api.responses import success
from app.core.config import get_settings
from app.db.session import get_db_session
from app.middleware.auth import get_google_token_verifier
from app.schemas.google_oidc_handoff import (
    AuthenticatedGoogleOidcHandoffResponse,
    GoogleOidcHandoffRequest,
    PendingGoogleOidcHandoffResponse,
)
from app.services.app_session_service import AppSessionPolicy, AppSessionService
from app.services.google_identity_codec import GoogleIdentityCodec
from app.services.google_oidc_handoff_auth import GoogleOidcHandoffAuthenticator
from app.services.google_oidc_handoff_service import (
    AuthenticatedGoogleHandoff,
    GoogleOidcHandoffService,
    PendingIdentityPolicy,
)
from app.services.service_dependencies import (
    get_google_identity_codec,
    get_google_oidc_handoff_authenticator,
)

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
