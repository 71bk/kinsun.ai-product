"""Live-authorized, transactional maintenance of staff-recorded elder data."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.cursor import decode_cursor, encode_cursor
from app.core.exceptions import ConflictError, NotFoundError, OptimisticConcurrencyError
from app.events.outbox_writer import write_outbox_entry
from app.models.actor import Actor
from app.models.care_profile import ElderCareProfileEntry
from app.models.elder import Elder
from app.models.elder_profile_change import ElderProfileChange
from app.repositories.elder_enrollment_repo import ElderEnrollmentRepository
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.elder_profile import (
    CareProfileListResponse,
    CareProfileResponse,
    CreateCareProfileRequest,
    ElderProfileResponse,
    ProfileChangeResponse,
    ProfileHistoryResponse,
    RetireCareProfileRequest,
    UpdateCareProfileRequest,
    UpdateElderProfileRequest,
)
from app.services.authorization_service import authorize_elder

PROFESSIONALS = {"DAYCARE_CARE_WORKER", "HOME_CARE_WORKER"}


def basic_snapshot(elder: Elder) -> ElderProfileResponse:
    return ElderProfileResponse(
        elder_id=elder.id,
        display_name=elder.display_name,
        preferred_name=elder.preferred_name,
        preferred_language=elder.preferred_language,
        profile_version=elder.profile_version,
    )


def care_snapshot(entry: ElderCareProfileEntry) -> CareProfileResponse:
    return CareProfileResponse(
        care_profile_entry_id=entry.id,
        elder_id=entry.elder_id,
        **{
            field: getattr(entry, field)
            for field in CareProfileResponse.model_fields
            if field not in {"care_profile_entry_id", "elder_id"}
        },
    )


def _page_query(stmt, model, cursor: str | None, limit: int):
    if cursor:
        created_at, resource_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                model.created_at < created_at,
                and_(model.created_at == created_at, model.id < resource_id),
            )
        )
    return stmt.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)


class ElderProfileService:
    def __init__(self, session: AsyncSession, actor: ActorContext):
        self.session = session
        self.actor = actor

    async def authorize(self, elder_id: UUID, *scopes: str) -> None:
        if self.actor.actor_role not in PROFESSIONALS or self.actor.status != "ACTIVE":
            raise NotFoundError("Resource not found")
        # Authentication ran before any lock wait; also recheck the live actor.
        current = (
            await self.session.execute(
                select(Actor.id).where(
                    Actor.id == self.actor.actor_id,
                    Actor.status == "ACTIVE",
                    Actor.actor_type == self.actor.actor_role,
                )
            )
        ).scalar_one_or_none()
        if current is None:
            raise NotFoundError("Resource not found")
        for scope in scopes:
            await authorize_elder(self.session, self.actor, elder_id, scope)
        active = (
            await self.session.execute(
                select(Elder.id, Elder.actor_id).where(
                    Elder.id == elder_id,
                    Elder.tenant_id == self.actor.tenant_id,
                    Elder.status == "ACTIVE",
                )
            )
        ).one_or_none()
        if active is None:
            raise NotFoundError("Resource not found")
        if active.actor_id is None:
            enrollment = await ElderEnrollmentRepository(
                self.session, self.actor.tenant_id
            ).get_active(
                elder_id=elder_id,
                current_time=datetime.now(UTC),
            )
            if enrollment is None:
                raise NotFoundError("Resource not found")

    async def _elder(self, elder_id: UUID, *, lock: bool = False) -> Elder:
        stmt = select(Elder).where(Elder.id == elder_id, Elder.tenant_id == self.actor.tenant_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        elder = (await self.session.execute(stmt)).scalar_one_or_none()
        if elder is None:
            raise NotFoundError("Resource not found")
        return elder

    async def profile(self, elder_id: UUID) -> ElderProfileResponse:
        await self.authorize(elder_id, "elder:basic:read")
        result = basic_snapshot(await self._elder(elder_id))
        await self.authorize(elder_id, "elder:basic:read")
        return result

    async def care_list(
        self, elder_id: UUID, cursor: str | None, limit: int, include_retired: bool
    ) -> CareProfileListResponse:
        await self.authorize(elder_id, "elder:basic:read", "care_profile:read")
        stmt = select(ElderCareProfileEntry).where(
            ElderCareProfileEntry.tenant_id == self.actor.tenant_id,
            ElderCareProfileEntry.elder_id == elder_id,
        )
        if not include_retired:
            stmt = stmt.where(ElderCareProfileEntry.verification_status != "RETIRED")
        rows = list(
            (
                await self.session.execute(_page_query(stmt, ElderCareProfileEntry, cursor, limit))
            ).scalars()
        )
        page = rows[:limit]
        result = CareProfileListResponse(
            items=[care_snapshot(row) for row in page],
            has_more=len(rows) > limit,
            next_cursor=encode_cursor(page[-1].created_at, page[-1].id)
            if len(rows) > limit
            else None,
        )
        await self.authorize(elder_id, "elder:basic:read", "care_profile:read")
        return result

    async def history(
        self, elder_id: UUID, cursor: str | None, limit: int
    ) -> ProfileHistoryResponse:
        await self.authorize(elder_id, "elder:basic:read", "care_profile:read")
        stmt = (
            select(ElderProfileChange, Actor.display_name)
            .join(
                Actor,
                Actor.id == ElderProfileChange.changed_by_actor_id,
            )
            .where(
                ElderProfileChange.tenant_id == self.actor.tenant_id,
                ElderProfileChange.elder_id == elder_id,
            )
        )
        rows = (
            await self.session.execute(_page_query(stmt, ElderProfileChange, cursor, limit))
        ).all()
        page = rows[:limit]
        result = ProfileHistoryResponse(
            items=[
                ProfileChangeResponse(
                    profile_change_id=row.id,
                    changed_by_name=name,
                    **{
                        field: getattr(row, field)
                        for field in ProfileChangeResponse.model_fields
                        if field not in {"profile_change_id", "changed_by_name"}
                    },
                )
                for row, name in page
            ],
            has_more=len(rows) > limit,
            next_cursor=encode_cursor(page[-1][0].created_at, page[-1][0].id)
            if len(rows) > limit
            else None,
        )
        await self.authorize(elder_id, "elder:basic:read", "care_profile:read")
        return result

    async def mutate(
        self,
        elder_id: UUID,
        request: UpdateElderProfileRequest
        | CreateCareProfileRequest
        | UpdateCareProfileRequest
        | RetireCareProfileRequest,
        *,
        operation: str,
        key: str,
        trace_id: str,
        entry_id: UUID | None = None,
    ) -> dict:
        is_basic = operation == "BASIC_UPDATED"
        scopes = (
            ("elder:basic:read", "elder:profile:update")
            if is_basic
            else ("elder:basic:read", "care_profile:read", "care_profile:write")
        )
        await self.authorize(elder_id, *scopes)
        elder = await self._elder(elder_id, lock=True)
        await self.authorize(elder_id, *scopes)
        idem = IdempotencyRepository(self.session, self.actor.tenant_id, self.actor.actor_id)
        replay = await idem.begin(
            key=key,
            operation=f"elder_profile:{operation}",
            payload={
                "elder_id": str(elder_id),
                "entry_id": str(entry_id) if entry_id else None,
                **request.model_dump(mode="json"),
            },
        )
        await self.authorize(elder_id, *scopes)
        if replay.replayed:
            if replay.response_body is None:
                raise ConflictError("Command receipt unavailable")
            return replay.response_body
        before = None
        entry = None
        now = datetime.now(UTC)
        if is_basic:
            assert isinstance(request, UpdateElderProfileRequest)
            self._version(elder.profile_version, request.expected_version)
            before = basic_snapshot(elder).model_dump(mode="json")
            elder.display_name = request.display_name
            elder.preferred_name = request.preferred_name
            elder.preferred_language = request.preferred_language
            elder.profile_version += 1
        elif operation == "CARE_ENTRY_CREATED":
            assert isinstance(request, CreateCareProfileRequest)
            count = (
                await self.session.execute(
                    select(func.count())
                    .select_from(ElderCareProfileEntry)
                    .where(
                        ElderCareProfileEntry.tenant_id == self.actor.tenant_id,
                        ElderCareProfileEntry.elder_id == elder_id,
                        ElderCareProfileEntry.verification_status != "RETIRED",
                    )
                )
            ).scalar_one()
            if count >= 20:
                raise ConflictError("Active care entry limit reached")
            entry = ElderCareProfileEntry(
                tenant_id=self.actor.tenant_id,
                elder_id=elder_id,
                category=request.category,
                content=request.content,
                source_type="STAFF_RECORDED",
                source_actor_id=self.actor.actor_id,
                verification_status="RECORDED",
                effective_from=now,
                version=1,
            )
            self.session.add(entry)
        else:
            assert isinstance(request, UpdateCareProfileRequest | RetireCareProfileRequest)
            entry = (
                await self.session.execute(
                    select(ElderCareProfileEntry)
                    .where(
                        ElderCareProfileEntry.id == entry_id,
                        ElderCareProfileEntry.tenant_id == self.actor.tenant_id,
                        ElderCareProfileEntry.elder_id == elder_id,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if entry is None:
                raise NotFoundError("Resource not found")
            await self.authorize(elder_id, *scopes)
            self._version(entry.version, request.expected_version)
            if entry.verification_status == "RETIRED":
                raise ConflictError("Entry is retired")
            before = care_snapshot(entry).model_dump(mode="json")
            if operation == "CARE_ENTRY_RETIRED":
                entry.verification_status = "RETIRED"
                entry.retired_at = now
            else:
                assert isinstance(request, UpdateCareProfileRequest)
                if entry.verification_status == "DISPUTED":
                    raise ConflictError("Disputed entry requires resolution before editing")
                entry.category, entry.content = request.category, request.content
                entry.source_type, entry.source_actor_id = "STAFF_RECORDED", self.actor.actor_id
                entry.verification_status, entry.effective_from = "RECORDED", now
            entry.version += 1
            entry.updated_at = now
        await self.session.flush()
        if entry is not None:
            await self.session.refresh(entry)
        after = (basic_snapshot(elder) if is_basic else care_snapshot(entry)).model_dump(
            mode="json"
        )
        version = elder.profile_version if is_basic else entry.version
        change = ElderProfileChange(
            tenant_id=self.actor.tenant_id,
            elder_id=elder_id,
            care_profile_entry_id=entry.id if entry else None,
            changed_by_actor_id=self.actor.actor_id,
            change_type=operation,
            resource_version=version,
            reason=request.reason,
            before_data=before,
            after_data=after,
        )
        self.session.add(change)
        await self.session.flush()
        await write_outbox_entry(
            self.session,
            event_type="elder.profile_changed.v1",
            aggregate_type="elder_profile_change",
            aggregate_id=change.id,
            tenant_id=self.actor.tenant_id,
            elder_id=elder_id,
            actor_id=self.actor.actor_id,
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=key,
            payload={
                "profile_change_id": str(change.id),
                "elder_id": str(elder_id),
                "care_profile_entry_id": str(entry.id) if entry else None,
                "change_type": operation,
                "resource_version": version,
            },
        )
        await idem.complete(
            key=key,
            resource_type="elder_profile_change",
            resource_id=change.id,
            response_status=201 if operation == "CARE_ENTRY_CREATED" else 200,
            response_body=after,
        )
        await self.authorize(elder_id, *scopes)
        return after

    @staticmethod
    def _version(actual: int, expected: int) -> None:
        if actual != expected:
            raise OptimisticConcurrencyError("Profile has changed; reload before retrying")
