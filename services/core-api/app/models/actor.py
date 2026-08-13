"""Actor ORM model.

Represents a system actor (elder, care worker, family member, admin, etc.).
An Actor can belong to multiple tenants via TenantMembership, so it does NOT
use TenantScopedMixin.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, pg_enum

#: eldercare_ai.actor_type_enum
ACTOR_TYPE_ENUM = pg_enum(
    "actor_type_enum",
    "ELDER",
    "DAYCARE_CARE_WORKER",
    "HOME_CARE_WORKER",
    "FAMILY_MEMBER",
    "ADMIN",
    "CONTENT_MANAGER",
    "SYSTEM_SERVICE",
)


class Actor(BaseModel):
    """System actor — any identity that can perform actions.

    Inherits id (mapped onto actor_id), created_at and updated_at from
    BaseModel. Does NOT use TenantScopedMixin because an Actor can belong to
    multiple tenants via TenantMembership, nor VersionedMixin because the
    baseline's actor table has no version column.
    """

    __tablename__ = "actor"
    __pk_name__ = "actor_id"

    actor_type: Mapped[str] = mapped_column(
        ACTOR_TYPE_ENUM,
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        sa.String(120),
        nullable=False,
    )
    email: Mapped[str | None] = mapped_column(
        sa.String(254),
        nullable=True,
    )
    phone: Mapped[str | None] = mapped_column(
        sa.String(32),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default=sa.text("'ACTIVE'"),
    )
