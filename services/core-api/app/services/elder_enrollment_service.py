"""Versioned accountless institution enrollment management, independent of care access."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.cursor import decode_cursor, encode_cursor
from app.core.exceptions import ConflictError, NotFoundError, OptimisticConcurrencyError
from app.events.outbox_writer import write_outbox_entry
from app.models.actor import Actor
from app.models.assisted_elder_session import AssistedElderSession
from app.models.care_assignment import CareAssignment
from app.models.care_relationship import CareRelationship
from app.models.care_unit import CareUnit
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.models.elder_enrollment import ElderEnrollment
from app.models.elder_enrollment_change import ElderEnrollmentChange
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.elder_enrollment import (
    EnrollmentChangeResponse,
    EnrollmentCommand,
    EnrollmentHistoryResponse,
    EnrollmentListResponse,
    EnrollmentResponse,
)

READ = "enrollment:read"
MANAGE = "enrollment:manage"
TRANSITIONS = {"suspend": ("ACTIVE", "SUSPENDED"), "resume": ("SUSPENDED", "ACTIVE")}


def _page(stmt, model, cursor, limit):
    if cursor:
        at, row_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(model.created_at < at, and_(model.created_at == at, model.id < row_id))
        )
    return stmt.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)


class ElderEnrollmentService:
    def __init__(self, session: AsyncSession, actor: ActorContext):
        self.session, self.actor = session, actor

    def _query(self, scope=READ):
        actor = self.actor
        if actor.actor_role != "DAYCARE_CARE_WORKER" or actor.status != "ACTIVE":
            raise NotFoundError("Resource not found")
        now = datetime.now(UTC)
        n, r, m = ElderEnrollment, CareRelationship, ActorTenantMembership

        def membership(unit):
            return exists(
                select(m.id).where(
                    m.actor_id == actor.actor_id,
                    m.tenant_id == actor.tenant_id,
                    m.care_unit_id.is_(None) if unit is None else m.care_unit_id == unit,
                    m.role_code == actor.actor_role,
                    m.status == "ACTIVE",
                    m.effective_from <= now,
                    or_(m.effective_to.is_(None), m.effective_to > now),
                )
            )

        def grant(required):
            return exists(
                select(r.id).where(
                    r.elder_id == n.elder_id,
                    r.tenant_id == n.tenant_id,
                    r.care_unit_id == n.care_unit_id,
                    r.actor_id == actor.actor_id,
                    r.relationship_type == "DAYCARE_ASSIGNMENT",
                    r.status == "ACTIVE",
                    r.effective_from <= now,
                    or_(r.effective_to.is_(None), r.effective_to > now),
                    r.scope.contains(list({READ, required})),
                ),
            )

        return (
            select(n, Elder.display_name, grant(MANAGE))
            .join(Elder, and_(Elder.id == n.elder_id, Elder.tenant_id == n.tenant_id))
            .where(
                grant(scope),
                n.tenant_id == actor.tenant_id,
                n.enrollment_type == "ORGANIZATION",
                n.created_by_actor_id == actor.actor_id,
                Elder.actor_id.is_(None),
                Elder.status == "ACTIVE",
                exists(
                    select(Actor.id).where(
                        Actor.id == actor.actor_id,
                        Actor.status == "ACTIVE",
                        Actor.actor_type == actor.actor_role,
                    )
                ),
                exists(
                    select(Tenant.id).where(Tenant.id == actor.tenant_id, Tenant.status == "ACTIVE")
                ),
                exists(
                    select(CareUnit.id).where(
                        CareUnit.id == n.care_unit_id,
                        CareUnit.tenant_id == actor.tenant_id,
                        CareUnit.status == "ACTIVE",
                    )
                ),
                membership(None),
                membership(n.care_unit_id),
            )
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def _response(row):
        n, name, can_manage = row
        return EnrollmentResponse(
            enrollment_id=n.id,
            elder_id=n.elder_id,
            display_name=name,
            care_unit_id=n.care_unit_id,
            status=n.status,
            version=n.version,
            valid_from=n.valid_from,
            valid_until=n.valid_until,
            ended_at=n.ended_at,
            can_manage=can_manage,
        )

    async def authorize(self, enrollment_id: UUID, scope=READ):
        rows = (
            await self.session.execute(
                self._query(scope).where(ElderEnrollment.id == enrollment_id)
            )
        ).all()
        if not rows:
            raise NotFoundError("Resource not found")
        return rows[0]

    async def list(self, cursor, limit):
        stmt = self._query()
        rows = (await self.session.execute(_page(stmt, ElderEnrollment, cursor, limit))).all()
        page = rows[:limit]
        return EnrollmentListResponse(
            items=[self._response(row) for row in page],
            has_more=len(rows) > limit,
            next_cursor=encode_cursor(page[-1][0].created_at, page[-1][0].id)
            if len(rows) > limit
            else None,
        )

    async def get(self, enrollment_id):
        return self._response(await self.authorize(enrollment_id))

    async def history(self, enrollment_id, cursor, limit):
        await self.authorize(enrollment_id)
        h = ElderEnrollmentChange
        rows = (
            await self.session.execute(
                _page(
                    select(h, Actor.display_name)
                    .join(Actor, Actor.id == h.changed_by_actor_id)
                    .where(h.enrollment_id == enrollment_id, h.tenant_id == self.actor.tenant_id),
                    h,
                    cursor,
                    limit,
                )
            )
        ).all()
        await self.authorize(enrollment_id)
        page = rows[:limit]
        return EnrollmentHistoryResponse(
            items=[
                EnrollmentChangeResponse(
                    enrollment_change_id=h.id,
                    changed_by_actor_id=h.changed_by_actor_id,
                    changed_by_name=name,
                    from_status=h.from_status,
                    to_status=h.to_status,
                    version=h.version,
                    reason=h.reason,
                    created_at=h.created_at,
                )
                for h, name in page
            ],
            has_more=len(rows) > limit,
            next_cursor=encode_cursor(page[-1][0].created_at, page[-1][0].id)
            if len(rows) > limit
            else None,
        )

    async def command(self, enrollment_id, action, body: EnrollmentCommand, key, trace_id):
        initial = await self.authorize(enrollment_id, MANAGE)
        # Match profile-write lock order; enrollment lock also serializes handoff issuance.
        await self.session.execute(
            select(Elder.id)
            .where(Elder.id == initial[0].elder_id, Elder.tenant_id == self.actor.tenant_id)
            .with_for_update()
        )
        await self.session.execute(
            select(ElderEnrollment.id)
            .where(
                ElderEnrollment.id == enrollment_id,
                ElderEnrollment.tenant_id == self.actor.tenant_id,
            )
            .with_for_update()
        )
        row = await self.authorize(enrollment_id, MANAGE)
        n = row[0]
        idem = IdempotencyRepository(self.session, self.actor.tenant_id, self.actor.actor_id)
        replay = await idem.begin(
            key=key,
            operation="enrollment_" + action,
            payload={"enrollment_id": enrollment_id, **body.model_dump(mode="json")},
        )
        if replay.replayed and replay.response_body is not None:
            return replay.response_body
        if n.version != body.expected_version:
            raise OptimisticConcurrencyError("Enrollment has changed; reload before retrying")
        now = datetime.now(UTC)
        if action == "end":
            target = "ENDED"
            allowed = n.status in {"ACTIVE", "SUSPENDED"}
        else:
            source, target = TRANSITIONS[action]
            allowed = n.status == source
        if not allowed:
            raise ConflictError("Enrollment transition is unavailable")
        if action == "resume" and (n.valid_from > now or (n.valid_until and n.valid_until <= now)):
            raise ConflictError("Enrollment period is unavailable")
        count = await self.session.scalar(
            select(func.count())
            .select_from(ElderEnrollment)
            .where(
                ElderEnrollment.tenant_id == self.actor.tenant_id,
                ElderEnrollment.elder_id == n.elder_id,
            )
        )
        if count != 1:
            raise ConflictError("Enrollment requires individual review")
        previous = n.status
        n.status, n.version = target, n.version + 1
        if target == "ENDED":
            n.ended_at, n.ended_reason = now, body.reason
        if target != "ACTIVE":
            await self._stop_service(n, now, key, trace_id)
        change = ElderEnrollmentChange(
            tenant_id=self.actor.tenant_id,
            enrollment_id=n.id,
            elder_id=n.elder_id,
            changed_by_actor_id=self.actor.actor_id,
            from_status=previous,
            to_status=target,
            version=n.version,
            reason=body.reason,
        )
        self.session.add(change)
        await self.session.flush()
        await write_outbox_entry(
            self.session,
            "elder.enrollment_changed.v1",
            "ElderEnrollment",
            n.id,
            self.actor.tenant_id,
            {
                "enrollment_id": str(n.id),
                "elder_id": str(n.elder_id),
                "from_status": previous,
                "to_status": target,
                "version": n.version,
            },
            trace_id,
            aggregate_version=n.version,
            elder_id=n.elder_id,
            actor_id=self.actor.actor_id,
        )
        result = self._response(row).model_dump(mode="json")
        await idem.complete(
            key=key,
            resource_type="elder_enrollment",
            resource_id=n.id,
            response_status=200,
            response_body=result,
        )
        return result

    async def _stop_service(self, enrollment, now, key, trace_id):
        s, c, a = AssistedElderSession, ConversationSession, CareAssignment
        scope = [s.enrollment_id == enrollment.id, s.tenant_id == self.actor.tenant_id]
        await self.session.execute(
            update(s)
            .where(*scope, s.status.in_(["PAIRING", "ACTIVE"]))
            .values(status="ENDED", ended_at=now, version=s.version + 1)
        )
        await self.session.execute(
            update(c)
            .where(
                c.tenant_id == self.actor.tenant_id,
                c.elder_id == enrollment.elder_id,
                c.state.notin_(["COMPLETED", "CANCELLED", "FAILED"]),
            )
            .values(state="CANCELLED", ended_at=now)
        )
        # Visits are cancelled rather than silently revived on resume.
        cancelled = (
            await self.session.execute(
                update(a)
                .where(
                    a.tenant_id == self.actor.tenant_id,
                    a.elder_id == enrollment.elder_id,
                    a.status.in_(["DRAFT", "CONFIRMED", "IN_PROGRESS"]),
                )
                .values(status="CANCELLED", version=a.version + 1)
                .returning(a.id, a.worker_id, a.version)
            )
        ).all()
        for assignment_id, worker_id, version in cancelled:
            await write_outbox_entry(
                self.session,
                "care.assignment.cancelled.v1",
                "care_assignment",
                assignment_id,
                self.actor.tenant_id,
                {
                    "assignment_id": str(assignment_id),
                    "worker_actor_id": str(worker_id),
                    "status": "CANCELLED",
                    "version": version,
                },
                trace_id,
                aggregate_version=version,
                elder_id=enrollment.elder_id,
                actor_id=self.actor.actor_id,
                idempotency_key=key,
                classification="CONFIDENTIAL",
            )
