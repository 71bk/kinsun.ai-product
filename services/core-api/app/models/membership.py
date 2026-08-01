"""ActorTenantMembership ORM model.

The baseline schema keeps tenant membership and care-unit membership in ONE
table, `eldercare_ai.actor_tenant_membership`, distinguished by whether
care_unit_id is set:

- care_unit_id IS NULL  → membership of the tenant as a whole
- care_unit_id IS NOT NULL → membership narrowed to that care unit

The branch this code came from modelled these as two separate tables. They are
merged here because two ORM classes cannot map the same table cleanly.
TenantMembershipRepository and CareUnitMembershipRepository both query this
model, each applying its own predicate.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin


class ActorTenantMembership(BaseModel, TenantScopedMixin):
    """An actor's membership in a tenant, optionally narrowed to a care unit.

    Inherits from BaseModel (id mapped onto membership_id, created_at,
    updated_at) and TenantScopedMixin (tenant_id).
    """

    __tablename__ = "actor_tenant_membership"
    __pk_name__ = "membership_id"

    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    care_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.care_unit.care_unit_id"),
        nullable=True,
    )
    role_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=sa.text("'ACTIVE'"),
        nullable=False,
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
