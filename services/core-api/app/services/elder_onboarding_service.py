"""Atomic institution onboarding for an accountless Elder care subject."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError, ValidationError
from app.models.care_profile import ElderCareProfileEntry
from app.models.care_relationship import CareRelationship
from app.models.care_unit import CareUnit
from app.models.elder import Elder
from app.models.elder_enrollment import ElderEnrollment
from app.repositories.care_profile_repo import CareProfileRepository
from app.repositories.care_unit_membership_repo import CareUnitMembershipRepository
from app.repositories.elder_enrollment_repo import ElderEnrollmentRepository
from app.repositories.elder_repo import ElderRepository
from app.schemas.assisted_elder import CreateAccountlessElderRequest

_CREATOR_SCOPE = [
    "elder:basic:read",
    "elder:access_context:read",
    "care_profile:read",
    "assisted_session:create",
    "voice_session:create",
    "voice_session:read",
    "voice_session:control",
    "consent:read",
]


@dataclass(frozen=True)
class AccountlessElderBundle:
    elder: Elder
    enrollment: ElderEnrollment
    relationship: CareRelationship
    care_profile: list[ElderCareProfileEntry]


class ElderOnboardingService:
    """Create only care-subject state; never creates an Actor or login identity."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._enrollments = ElderEnrollmentRepository(session, tenant_id)
        self._care_profile = CareProfileRepository(session, tenant_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        actor_context: ActorContext,
        request: CreateAccountlessElderRequest,
    ) -> AccountlessElderBundle:
        if (
            organization_id != actor_context.tenant_id
            or actor_context.tenant_id != self._tenant_id
            or actor_context.actor_role != "DAYCARE_CARE_WORKER"
        ):
            raise NotFoundError("Resource not found")
        if request.primary_care_setting not in {"DAYCARE", "COMMUNITY"}:
            raise ValidationError(
                [
                    {
                        "field": "primary_care_setting",
                        "reason": "DAYCARE_STAFF_REQUIRES_INSTITUTION_SETTING",
                    }
                ]
            )

        now = datetime.now(UTC)
        care_unit = await self._session.scalar(
            select(CareUnit).where(
                CareUnit.id == request.care_unit_id,
                CareUnit.tenant_id == self._tenant_id,
                CareUnit.status == "ACTIVE",
            )
        )
        is_member = await CareUnitMembershipRepository(self._session).is_member(
            actor_context.actor_id,
            request.care_unit_id,
            self._tenant_id,
            actor_context.actor_role,
            now,
        )
        if care_unit is None or not is_member:
            raise NotFoundError("Resource not found")

        elder = Elder(
            actor_id=None,
            tenant_id=self._tenant_id,
            primary_care_unit_id=request.care_unit_id,
            display_name=request.display_name,
            preferred_name=request.preferred_name,
            preferred_language=request.preferred_language,
            primary_care_setting=request.primary_care_setting,
            response_length_preference=request.response_length_preference,
            timezone=request.timezone,
            status="ACTIVE",
        )
        self._session.add(elder)
        await self._session.flush()

        enrollment = ElderEnrollment(
            tenant_id=self._tenant_id,
            elder_id=elder.id,
            care_unit_id=request.care_unit_id,
            enrollment_type="ORGANIZATION",
            status="ACTIVE",
            valid_from=now,
            created_by_actor_id=actor_context.actor_id,
        )
        self._enrollments.add(enrollment)

        relationship = CareRelationship(
            tenant_id=self._tenant_id,
            elder_id=elder.id,
            actor_id=actor_context.actor_id,
            care_unit_id=request.care_unit_id,
            relationship_type="DAYCARE_ASSIGNMENT",
            scope=list(_CREATOR_SCOPE),
            status="ACTIVE",
            effective_from=now,
        )
        self._session.add(relationship)
        await self._session.flush()

        entries: list[ElderCareProfileEntry] = []
        for item in request.care_profile:
            entry = ElderCareProfileEntry(
                tenant_id=self._tenant_id,
                elder_id=elder.id,
                category=item.category,
                content=item.content,
                source_type="STAFF_RECORDED",
                source_actor_id=actor_context.actor_id,
                verification_status="RECORDED",
                effective_from=now,
                version=1,
            )
            self._care_profile.add(entry)
            entries.append(entry)
        await self._care_profile.flush()
        return AccountlessElderBundle(elder, enrollment, relationship, entries)
    async def get_created_bundle(
        self,
        *,
        elder_id: UUID,
        actor_context: ActorContext,
    ) -> AccountlessElderBundle | None:
        elder = await ElderRepository(self._session, self._tenant_id).get_by_id(elder_id)
        if elder is None or elder.actor_id is not None:
            return None
        enrollment = await self._enrollments.get_created_for_elder(
            elder_id=elder_id,
            actor_id=actor_context.actor_id,
        )
        relationship = await self._session.scalar(
            select(CareRelationship)
            .where(
                CareRelationship.tenant_id == self._tenant_id,
                CareRelationship.elder_id == elder_id,
                CareRelationship.actor_id == actor_context.actor_id,
                CareRelationship.relationship_type == "DAYCARE_ASSIGNMENT",
            )
            .order_by(CareRelationship.created_at.desc())
            .limit(1)
        )
        if enrollment is None or relationship is None:
            return None
        entries = await self._care_profile.list_for_elder(elder_id)
        return AccountlessElderBundle(elder, enrollment, relationship, entries)
