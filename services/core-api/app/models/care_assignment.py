"""CareAssignment ORM model.

Represents a time-bounded assignment of a care worker to an elder
within a specific care unit. Used for fine-grained, time-scoped
authorization — the worker can only access elder data during the
active service window.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin, VersionedMixin


class CareAssignment(BaseModel, TenantScopedMixin, VersionedMixin):
    """Time-bounded care assignment: Worker → Elder within a CareUnit.

    Inherits from BaseModel (id mapped onto assignment_id, created_at,
    updated_at), TenantScopedMixin (tenant_id) and VersionedMixin — this is
    the one baseline table that carries a version column.

    A CareAssignment grants a worker access to an elder's data for
    a specific service window (service_start → service_end). Once
    the window expires or the assignment is cancelled, access is
    immediately revoked.

    The Python attribute stays `worker_id`; the underlying column is
    `worker_actor_id`, which is how the baseline names it.
    """

    __tablename__ = "care_assignment"
    __pk_name__ = "assignment_id"

    care_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.care_unit.care_unit_id"),
        nullable=False,
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        "worker_actor_id",
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=False,
    )
    service_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    service_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    service_scope: Mapped[list] = mapped_column(
        JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        server_default=sa.text("'DRAFT'"),
        nullable=False,
    )
