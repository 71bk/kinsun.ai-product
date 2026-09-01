"""Accountless Elder onboarding and limited staff-assisted tablet sessions."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.agent_runtime import get_agent_runtime_client
from app.api.responses import get_correlation_id, success
from app.core.agent_runtime import AgentRuntimePort
from app.core.auth import ActorContext
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.db.session import get_db_session
from app.domain.consent import ConsentPurpose
from app.domain.conversation import ConversationStartCommand, LanguageRoute
from app.middleware.actor_guard import require_active_actor
from app.models.policy import PolicyRegistry
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.assisted_elder import (
    AccountlessElderResponse,
    AcknowledgeFirstUseRequest,
    ActivatedAssistedSessionResponse,
    AssistedCompanionTurnRequest,
    CareProfileEntryResponse,
    CreateAccountlessElderRequest,
    CurrentAssistedSessionResponse,
    EndAssistedSessionResponse,
    ExchangeAssistedSessionRequest,
    FirstUseAcknowledgementResponse,
    IssueAssistedSessionRequest,
    IssuedAssistedSessionResponse,
)
from app.services.assisted_elder_session_service import (
    AssistedElderSessionPolicy,
    AssistedElderSessionService,
)
from app.services.assisted_session_tokens import AssistedSessionTokenCodec
from app.services.companion_service import CompanionService
from app.services.consent_service import ConsentService
from app.services.conversation_service import ConversationService
from app.services.elder_onboarding_service import (
    AccountlessElderBundle,
    ElderOnboardingService,
)

router = APIRouter(prefix="/api/v1", tags=["assisted-elder-sessions"])
_AUTHENTICATION_REQUIRED = "Assisted Elder Session is unavailable"


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _require_feature_enabled() -> None:
    if not get_settings().assisted_elder_sessions_enabled:
        raise ServiceUnavailableError("Assisted Elder Session is not enabled")


def _assisted_service(session: AsyncSession) -> AssistedElderSessionService:
    settings = get_settings()
    return AssistedElderSessionService(
        session,
        AssistedElderSessionPolicy.from_settings(settings),
        enabled=settings.assisted_elder_sessions_enabled,
    )


def _accountless_elder_response(bundle: AccountlessElderBundle) -> dict:
    return AccountlessElderResponse(
        elder_id=bundle.elder.id,
        actor_id=None,
        enrollment_id=bundle.enrollment.id,
        relationship_id=bundle.relationship.id,
        display_name=bundle.elder.display_name,
        preferred_name=bundle.elder.preferred_name,
        preferred_language=bundle.elder.preferred_language,
        primary_care_setting=bundle.elder.primary_care_setting,
        care_unit_id=bundle.enrollment.care_unit_id,
        care_profile=[
            CareProfileEntryResponse(
                care_profile_entry_id=entry.id,
                category=entry.category,
                content=entry.content,
                source_type=entry.source_type,
                verification_status=entry.verification_status,
                version=entry.version,
            )
            for entry in bundle.care_profile
        ],
    ).model_dump(mode="json")


async def _first_use_acknowledgement(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    elder_id: UUID,
) -> FirstUseAcknowledgementResponse:
    settings = get_settings()
    try:
        consent = await ConsentService(session, tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.BASIC_VOICE,
        )
    except NotFoundError:
        return FirstUseAcknowledgementResponse(
            status="REQUIRED",
            policy_version=settings.assisted_elder_acknowledgement_policy_version,
        )

    policy = await session.get(PolicyRegistry, consent.policy_id)
    return FirstUseAcknowledgementResponse(
        status="ACKNOWLEDGED",
        policy_version=(
            policy.version
            if policy is not None
            else settings.assisted_elder_acknowledgement_policy_version
        ),
        consent_version=consent.version,
        acknowledged_at=consent.granted_at,
        confirmation_method=consent.confirmation_method,
    )


def assisted_session_bearer(request: Request) -> str:
    values = request.headers.getlist("authorization")
    if len(values) != 1:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    scheme, separator, token = values[0].partition(" ")
    if separator != " " or scheme.casefold() != "bearer":
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)
    try:
        AssistedSessionTokenCodec().digest_session(token)
    except ValueError:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
    return token


@router.post(
    "/organizations/{organization_id}/elders",
    status_code=status.HTTP_201_CREATED,
)
async def create_accountless_elder(
    request: CreateAccountlessElderRequest,
    organization_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _require_feature_enabled()
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_accountless_elder",
        payload={"organization_id": organization_id, **request.model_dump(mode="json")},
    )
    service = ElderOnboardingService(session, actor_context.tenant_id)
    if replay.replayed:
        bundle = (
            await service.get_created_bundle(
                elder_id=replay.resource_id,
                actor_context=actor_context,
            )
            if replay.resource_id is not None
            else None
        )
        if bundle is None:
            raise NotFoundError("Resource not found")
    else:
        bundle = await service.create(
            organization_id=organization_id,
            actor_context=actor_context,
            request=request,
        )
        response_body = _accountless_elder_response(bundle)
        await idem.complete(
            key=idempotency_key,
            resource_type="elder",
            resource_id=bundle.elder.id,
            response_status=status.HTTP_201_CREATED,
            response_body=response_body,
        )
    return success(_accountless_elder_response(bundle))


@router.post(
    "/elders/{elder_id}/assisted-sessions",
    status_code=status.HTTP_201_CREATED,
)
async def issue_assisted_session(
    _request: IssueAssistedSessionRequest,
    response: Response,
    elder_id: UUID = Path(...),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    issued = await _assisted_service(session).issue(
        actor_context=actor_context,
        elder_id=elder_id,
    )
    _no_store(response)
    return success(
        IssuedAssistedSessionResponse(
            assisted_session_id=issued.assisted_session.id,
            elder_id=issued.assisted_session.elder_id,
            pairing_token=issued.pairing_token,
            pairing_expires_at=issued.assisted_session.pairing_expires_at,
            absolute_expires_at=issued.assisted_session.absolute_expires_at,
        ).model_dump(mode="json")
    )


@router.post("/assisted-elder-sessions/exchange")
async def exchange_assisted_session(
    request: ExchangeAssistedSessionRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    activated = await _assisted_service(session).exchange(request.pairing_token)
    _no_store(response)
    return success(
        ActivatedAssistedSessionResponse(
            assisted_session_id=activated.assisted_session.id,
            elder_id=activated.assisted_session.elder_id,
            display_name=activated.elder.display_name,
            preferred_name=activated.elder.preferred_name,
            session_token=activated.session_token,
            idle_expires_at=activated.assisted_session.idle_expires_at,
            absolute_expires_at=activated.assisted_session.absolute_expires_at,
        ).model_dump(mode="json")
    )


@router.get("/assisted-elder-sessions/current")
async def get_current_assisted_session(
    response: Response,
    token: str = Depends(assisted_session_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    resolved = await _assisted_service(session).resolve_current(
        token,
        requested_action="voice_session:read",
    )
    _no_store(response)
    acknowledgement = await _first_use_acknowledgement(
        session,
        tenant_id=resolved.actor_context.tenant_id,
        elder_id=resolved.elder.id,
    )
    return success(
        CurrentAssistedSessionResponse(
            assisted_session_id=resolved.assisted_session.id,
            elder_id=resolved.assisted_session.elder_id,
            display_name=resolved.elder.display_name,
            preferred_name=resolved.elder.preferred_name,
            status="ACTIVE",
            idle_expires_at=resolved.assisted_session.idle_expires_at,
            absolute_expires_at=resolved.assisted_session.absolute_expires_at,
            first_use_acknowledgement=acknowledgement,
        ).model_dump(mode="json")
    )


@router.post(
    "/assisted-elder-sessions/current/first-use-acknowledgement",
)
async def acknowledge_assisted_first_use(
    request: AcknowledgeFirstUseRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    token: str = Depends(assisted_session_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    resolved = await _assisted_service(session).resolve_current(
        token,
        requested_action="voice_session:create",
    )
    settings = get_settings()
    idem = IdempotencyRepository(
        session,
        resolved.actor_context.tenant_id,
        resolved.actor_context.actor_id,
    )
    replay = await idem.begin(
        key=idempotency_key,
        operation="acknowledge_assisted_first_use",
        payload={
            "assisted_session_id": resolved.assisted_session.id,
            "acknowledged": request.acknowledged,
            "policy_version": settings.assisted_elder_acknowledgement_policy_version,
        },
    )
    consent_service = ConsentService(session, resolved.actor_context.tenant_id)
    if replay.replayed:
        consent = (
            await consent_service.get_by_id(resolved.elder.id, replay.resource_id)
            if replay.resource_id is not None
            else None
        )
        if consent is None:
            raise NotFoundError("Resource not found")
    else:
        consent = await consent_service.acknowledge_assisted_basic_voice(
            elder_id=resolved.elder.id,
            recorded_by_actor_id=resolved.actor_context.actor_id,
            assisted_session_id=resolved.assisted_session.id,
            policy_version=settings.assisted_elder_acknowledgement_policy_version,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )

    acknowledgement = await _first_use_acknowledgement(
        session,
        tenant_id=resolved.actor_context.tenant_id,
        elder_id=resolved.elder.id,
    )
    payload = acknowledgement.model_dump(mode="json")
    if not replay.replayed:
        await idem.complete(
            key=idempotency_key,
            resource_type="consent_grant",
            resource_id=consent.id,
            response_status=200,
            response_body=payload,
        )
    _no_store(response)
    return success(payload)


@router.post(
    "/assisted-elder-sessions/current/first-use-acknowledgement/revoke",
)
async def revoke_assisted_first_use(
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    token: str = Depends(assisted_session_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    resolved = await _assisted_service(session).resolve_current(
        token,
        requested_action="voice_session:control",
    )
    idem = IdempotencyRepository(
        session,
        resolved.actor_context.tenant_id,
        resolved.actor_context.actor_id,
    )
    replay = await idem.begin(
        key=idempotency_key,
        operation="revoke_assisted_first_use",
        payload={"assisted_session_id": resolved.assisted_session.id},
    )
    if not replay.replayed:
        consent = await ConsentService(
            session,
            resolved.actor_context.tenant_id,
        ).revoke_assisted_basic_voice(
            elder_id=resolved.elder.id,
            recorded_by_actor_id=resolved.actor_context.actor_id,
            assisted_session_id=resolved.assisted_session.id,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
    acknowledgement = FirstUseAcknowledgementResponse(
        status="REQUIRED",
        policy_version=get_settings().assisted_elder_acknowledgement_policy_version,
    )
    payload = acknowledgement.model_dump(mode="json")
    if not replay.replayed:
        await idem.complete(
            key=idempotency_key,
            resource_type="consent_grant",
            resource_id=consent.id,
            response_status=200,
            response_body=payload,
        )
    _no_store(response)
    return success(payload)


@router.post("/assisted-elder-sessions/current/companion-turns")
async def create_assisted_companion_turn(
    request: AssistedCompanionTurnRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    token: str = Depends(assisted_session_bearer),
    session: AsyncSession = Depends(get_db_session),
    runtime_client: AgentRuntimePort = Depends(get_agent_runtime_client),
) -> dict:
    resolved = await _assisted_service(session).resolve_current(
        token,
        requested_action="voice_session:create",
    )
    idem = IdempotencyRepository(
        session,
        resolved.actor_context.tenant_id,
        resolved.actor_context.actor_id,
    )
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_assisted_companion_turn",
        payload={
            "assisted_session_id": resolved.assisted_session.id,
            "input_text": request.input_text,
        },
    )
    if replay.replayed:
        raise ConflictError("Companion turn already completed; create a new turn")

    conversation = await ConversationService(
        session,
        resolved.actor_context.tenant_id,
    ).create(
        elder_id=resolved.elder.id,
        actor_id=resolved.actor_context.actor_id,
        actor_role=resolved.actor_context.actor_role,
        command=ConversationStartCommand(
            language_route=LanguageRoute(resolved.elder.preferred_language),
            input_mode="text",
        ),
        trace_id=get_correlation_id(),
        idempotency_key=idempotency_key,
    )
    settings = get_settings()
    turn = await CompanionService(
        session,
        resolved.actor_context.tenant_id,
        runtime_client,
        settings.agent_runtime_model_id,
    ).run_turn(
        conversation=conversation,
        actor_context=resolved.actor_context,
        input_text=request.input_text,
        correlation_id=get_correlation_id(),
        idempotency_key=idempotency_key,
        latency_budget_ms=min(
            300_000,
            max(100, round(settings.agent_runtime_timeout_seconds * 1000)),
        ),
    )
    await idem.complete(
        key=idempotency_key,
        resource_type="agent_run",
        resource_id=turn.agent_run_id,
        response_status=200,
        response_body=turn.model_dump(mode="json"),
    )
    _no_store(response)
    return success(turn.model_dump(mode="json"))


@router.post("/assisted-elder-sessions/current/end")
async def end_assisted_session(
    response: Response,
    token: str = Depends(assisted_session_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _assisted_service(session).end(token)
    _no_store(response)
    return success(EndAssistedSessionResponse().model_dump(mode="json"))
