"""Administrator invitation UI and private activation boundary."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.kinsun_email_auth import require_kinsun_auth_bff
from app.api.responses import get_correlation_id, success
from app.bootstrap.dependencies import get_kinsun_identity_codec, get_password_hasher
from app.core.auth import ActorContext
from app.core.exceptions import ConflictError, NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.staff_invitation import (
    AcceptedStaffInvitationResponse,
    AcceptStaffInvitationRequest,
    CreateStaffInvitationRequest,
    RevokeStaffInvitationRequest,
)
from app.services.kinsun_identity_codec import KinsunIdentityCodec
from app.services.password_hasher import PasswordHasher
from app.services.staff_invitation_service import StaffInvitationService, require_staff_invitations


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


router = APIRouter(
    tags=["staff-invitations"], dependencies=[Depends(require_staff_invitations), Depends(no_store)]
)


def service(
    session: AsyncSession = Depends(get_db_session),
    codec: KinsunIdentityCodec = Depends(get_kinsun_identity_codec),
    hasher: PasswordHasher = Depends(get_password_hasher),
) -> StaffInvitationService:
    return StaffInvitationService(session, codec, hasher)


@router.get("/api/v1/admin/care-units")
async def list_care_units(
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=20, ge=1, le=100),
    actor: ActorContext = Depends(require_active_actor),
    invitations: StaffInvitationService = Depends(service),
) -> dict:
    return success((await invitations.units(actor, cursor, limit)).model_dump(mode="json"))


@router.get("/api/v1/admin/staff-invitations")
async def list_staff_invitations(
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=20, ge=1, le=100),
    actor: ActorContext = Depends(require_active_actor),
    invitations: StaffInvitationService = Depends(service),
) -> dict:
    return success((await invitations.list(actor, cursor, limit)).model_dump(mode="json"))


@router.post("/api/v1/admin/staff-invitations", status_code=201)
async def create_staff_invitation(
    request: CreateStaffInvitationRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160),
    actor: ActorContext = Depends(require_active_actor),
    invitations: StaffInvitationService = Depends(service),
) -> dict:
    await invitations.require_admin(actor)
    idem = IdempotencyRepository(invitations.session, actor.tenant_id, actor.actor_id)
    # Hash the email in the fingerprint source too; never retain the invitation credential.
    payload = request.model_dump(mode="json")
    payload["email"] = invitations.codec.digest_email(request.email)
    replay = await idem.begin(
        key=idempotency_key, operation="create_staff_invitation", payload=payload
    )
    if replay.replayed:
        raise ConflictError("Invitation already issued; its link is shown only once")
    result = await invitations.create(actor, request, get_correlation_id(), idempotency_key)
    await idem.complete(
        key=idempotency_key,
        resource_type="staff_invitation",
        resource_id=result.invitation_id,
        response_status=201,
        response_body={"invitation_id": str(result.invitation_id)},
    )
    return success(result.model_dump(mode="json"))


@router.post("/api/v1/admin/staff-invitations/{invitation_id}/revoke")
async def revoke_staff_invitation(
    invitation_id: UUID,
    request: RevokeStaffInvitationRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160),
    actor: ActorContext = Depends(require_active_actor),
    invitations: StaffInvitationService = Depends(service),
) -> dict:
    repo = await invitations.require_admin(actor)
    if await repo.get(invitation_id) is None:
        raise NotFoundError("Resource not found")
    idem = IdempotencyRepository(invitations.session, actor.tenant_id, actor.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="revoke_staff_invitation",
        payload={"invitation_id": str(invitation_id), "expected_version": request.expected_version},
    )
    if replay.replayed:
        return success(replay.response_body)
    result = await invitations.revoke(
        actor, invitation_id, request.expected_version, get_correlation_id(), idempotency_key
    )
    body = result.model_dump(mode="json")
    await idem.complete(
        key=idempotency_key,
        resource_type="staff_invitation",
        resource_id=invitation_id,
        response_status=200,
        response_body=body,
    )
    return success(body)


@router.post("/api/v1/internal/auth/staff-invitations/accept")
async def accept_staff_invitation(
    request: AcceptStaffInvitationRequest,
    _: None = Depends(require_kinsun_auth_bff),
    invitations: StaffInvitationService = Depends(service),
) -> dict:
    await invitations.accept(request, get_correlation_id())
    return success(AcceptedStaffInvitationResponse().model_dump(mode="json"))
