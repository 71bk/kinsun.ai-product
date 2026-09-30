"""SQL gate for institution access; preserve legacy elders without enrollments."""

from sqlalchemy import exists, or_, select

from app.models.elder_enrollment import ElderEnrollment


def enrollment_allows_service(tenant_id, elder_id, now):
    # Any unavailable institutional enrollment blocks ordinary institutional
    # access. This slice cannot create overlapping or replacement enrollments.
    return ~exists(
        select(ElderEnrollment.id).where(
            ElderEnrollment.tenant_id == tenant_id,
            ElderEnrollment.elder_id == elder_id,
            ElderEnrollment.enrollment_type == "ORGANIZATION",
            or_(
                ElderEnrollment.status != "ACTIVE",
                ElderEnrollment.valid_from > now,
                ElderEnrollment.valid_until <= now,
            ),
        )
    )
