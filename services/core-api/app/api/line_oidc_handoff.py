"""Private BFF-to-Core LINE OIDC handoff and onboarding endpoints."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.app_sessions import app_session_bearer
from app.api.responses import get_correlation_id, success
from app.bootstrap.dependencies import (
    get_family_invitation_token_codec,
    get_line_identity_codec,
    get_line_oidc_handoff_authenticator,
)
from app.core.auth import ActorContext
from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.core.oidc import LineTokenVerifier
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.middleware.auth import get_line_token_verifier
from app.repositories.account_identity_repo import AccountIdentityRepository
from app.schemas.line_oidc_handoff import (
    AuthenticatedLineOidcHandoffResponse,
    CompletedLineOnboardingResponse,
    CompleteLineOnboardingRequest,
    ConfirmLineAccountMergeRequest,
    LineAccountManualReviewResponse,
    LineAccountMergeRequiredResponse,
    LineIdentityMethodStatusResponse,
    LineOidcHandoffRequest,
    LinkedLineIdentityResponse,
    LinkLineIdentityRequest,
    MergedLineAccountResponse,
    PendingLineOidcHandoffResponse,
)
from app.services.account_identity_link_service import (
    AccountIdentityLinkService,
    AccountIdentityStatusService,
    LinkedIdentity,
    MergeCompleted,
    MergeRequired,
)
from app.services.app_session_service import AppSessionPolicy, AppSessionService
from app.services.family_invitation_service import FamilyInvitationService
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec
from app.services.google_oidc_handoff_service import PendingIdentityPolicy
from app.services.line_identity_codec import LineIdentityCodec
from app.services.line_oidc_handoff_auth import LineOidcHandoffAuthenticator
from app.services.line_oidc_handoff_service import (
    AuthenticatedLineHandoff,
    LineOidcHandoffService,
)
from app.services.pending_google_onboarding_service import PendingGoogleOnboardingService

router = APIRouter(prefix="/api/v1/internal/auth/line", tags=["internal-auth"])


def require_line_oidc_bff(
    request: Request,
    authenticator: LineOidcHandoffAuthenticator = Depends(get_line_oidc_handoff_authenticator),
) -> None:
    authenticator.authenticate(request.headers.getlist("x-kinsun-bff-authorization"))


def _account_link_service(
    session: AsyncSession,
    *,
    verifier: LineTokenVerifier,
    identity_codec: LineIdentityCodec,
) -> AccountIdentityLinkService:
    settings = get_settings()
    policy = AppSessionPolicy.from_settings(settings)
    return AccountIdentityLinkService(
        session,
        verifier=verifier,
        identity_codec=identity_codec,
        app_session_service=AppSessionService(session, policy),
        merge_ttl=timedelta(seconds=settings.line_account_merge_ttl_seconds),
    )


@router.get("/status", status_code=status.HTTP_200_OK)
async def line_identity_method_status(
    response: Response,
    _: None = Depends(require_line_oidc_bff),
    actor_context: ActorContext = Depends(require_active_actor),
    app_session_token: str = Depends(app_session_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    settings = get_settings()
    policy = AppSessionPolicy.from_settings(settings)
    result = await AccountIdentityStatusService(
        repository=AccountIdentityRepository(session),
        app_session_service=AppSessionService(session, policy),
    ).status(
        actor_context=actor_context,
        app_session_token=app_session_token,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    payload = LineIdentityMethodStatusResponse(
        google_linked=result.google_linked,
        line_linked=result.line_linked,
        recently_authenticated=result.recently_authenticated,
    )
    return success(payload.model_dump(mode="json"))


@router.post("/link", status_code=status.HTTP_200_OK)
async def link_line_identity(
    body: LinkLineIdentityRequest,
    response: Response,
    _: None = Depends(require_line_oidc_bff),
    actor_context: ActorContext = Depends(require_active_actor),
    app_session_token: str = Depends(app_session_bearer),
    verifier: LineTokenVerifier = Depends(get_line_token_verifier),
    session: AsyncSession = Depends(get_db_session),
    identity_codec: LineIdentityCodec = Depends(get_line_identity_codec),
) -> dict:
    result = await _account_link_service(
        session,
        verifier=verifier,
        identity_codec=identity_codec,
    ).link_line(
        actor_context=actor_context,
        app_session_token=app_session_token,
        id_token=body.id_token,
        expected_nonce=body.expected_nonce,
        trace_id=get_correlation_id(),
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    if isinstance(result, LinkedIdentity):
        payload = LinkedLineIdentityResponse(status=result.status)
    elif isinstance(result, MergeRequired):
        payload = LineAccountMergeRequiredResponse(
            merge_token=result.token,
            expires_at=result.expires_at,
        )
    else:
        payload = LineAccountManualReviewResponse()
    return success(payload.model_dump(mode="json"))


@router.post("/merge/confirm", status_code=status.HTTP_200_OK)
async def confirm_line_account_merge(
    body: ConfirmLineAccountMergeRequest,
    response: Response,
    _: None = Depends(require_line_oidc_bff),
    actor_context: ActorContext = Depends(require_active_actor),
    app_session_token: str = Depends(app_session_bearer),
    verifier: LineTokenVerifier = Depends(get_line_token_verifier),
    session: AsyncSession = Depends(get_db_session),
    identity_codec: LineIdentityCodec = Depends(get_line_identity_codec),
) -> dict:
    result = await _account_link_service(
        session,
        verifier=verifier,
        identity_codec=identity_codec,
    ).confirm_merge(
        actor_context=actor_context,
        app_session_token=app_session_token,
        merge_token=body.merge_token,
        trace_id=get_correlation_id(),
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    if isinstance(result, MergeCompleted):
        payload = MergedLineAccountResponse(
            session_token=result.session.token,
            idle_expires_at=result.session.idle_expires_at,
            absolute_expires_at=result.session.absolute_expires_at,
        )
    else:
        payload = LineAccountManualReviewResponse()
    return success(payload.model_dump(mode="json"))


@router.post("/handoff", status_code=status.HTTP_200_OK)
async def handoff_line_oidc(
    request: LineOidcHandoffRequest,
    response: Response,
    _: None = Depends(require_line_oidc_bff),
    verifier: LineTokenVerifier = Depends(get_line_token_verifier),
    session: AsyncSession = Depends(get_db_session),
    identity_codec: LineIdentityCodec = Depends(get_line_identity_codec),
) -> dict:
    settings = get_settings()
    result = await LineOidcHandoffService(
        session,
        verifier=verifier,
        identity_codec=identity_codec,
        app_session_service=AppSessionService(
            session,
            AppSessionPolicy.from_settings(settings),
        ),
        pending_policy=PendingIdentityPolicy(
            timedelta(seconds=settings.line_pending_identity_ttl_seconds)
        ),
        allow_new_accounts=not settings.kinsun_native_auth_enabled,
    ).handoff(
        id_token=request.id_token,
        expected_nonce=request.expected_nonce,
        intent=request.intent,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    if isinstance(result, AuthenticatedLineHandoff):
        payload = AuthenticatedLineOidcHandoffResponse(
            session_token=result.session.token,
            idle_expires_at=result.session.idle_expires_at,
            absolute_expires_at=result.session.absolute_expires_at,
        )
    else:
        payload = PendingLineOidcHandoffResponse(
            pending_token=result.token,
            expires_at=result.expires_at,
        )
    return success(payload.model_dump(mode="json"))


@router.post("/onboarding", status_code=status.HTTP_200_OK)
async def complete_line_onboarding(
    request: CompleteLineOnboardingRequest,
    response: Response,
    _: None = Depends(require_line_oidc_bff),
    session: AsyncSession = Depends(get_db_session),
    invitation_codec: FamilyInvitationTokenCodec = Depends(get_family_invitation_token_codec),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
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
            f"line-onboarding:{request.pending_token}".encode("ascii")
        ).hexdigest()

    result = await PendingGoogleOnboardingService(
        session,
        app_session_service=AppSessionService(
            session,
            AppSessionPolicy.from_settings(settings),
        ),
        family_invitation_service=FamilyInvitationService(session, invitation_codec),
        provider="LINE",
    ).complete(
        pending_token=request.pending_token,
        invitation_code=request.invitation_code,
        display_name=request.display_name,
        trace_id=get_correlation_id(),
        idempotency_key=operation_key,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    payload = CompletedLineOnboardingResponse(
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
