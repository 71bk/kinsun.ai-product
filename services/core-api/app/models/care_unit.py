"""CareUnit ORM model.

Represents a care unit (daycare center, community site, home care agency)
that belongs to exactly one Tenant.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, TenantScopedMixin, pg_enum

#: eldercare_ai.care_unit_type_enum
CARE_UNIT_TYPE_ENUM = pg_enum(
    "care_unit_type_enum",
    "DAYCARE_CENTER",
    "COMMUNITY_SITE",
    "HOME_CARE_AGENCY",
)


class CareUnit(BaseModel, TenantScopedMixin):
    """Care Unit belongs to exactly one Tenant.

    Inherits from BaseModel (id mapped onto care_unit_id, created_at,
    updated_at) and TenantScopedMixin (tenant_id).
    """

    __tablename__ = "care_unit"
    __pk_name__ = "care_unit_id"

    unit_type: Mapped[str] = mapped_column(
        CARE_UNIT_TYPE_ENUM,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=sa.text("'ACTIVE'"),
        nullable=False,
    )
    address_text: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        server_default=sa.text("'Asia/Taipei'"),
        nullable=False,
    )
