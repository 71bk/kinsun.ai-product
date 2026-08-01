"""Policy registry ORM model.

Consent grants must reference an ACTIVE consent policy.  The policy row is
resolved by the Core API from the trusted tenant context and requested policy
version; clients never get to bypass policy status or effective-period checks.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel


class PolicyRegistry(BaseModel):
    """Versioned machine-readable policy registered for controlled use."""

    __tablename__ = "policy_registry"
    __pk_name__ = "policy_id"

    owner_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.tenant.tenant_id"),
        nullable=True,
    )
    policy_code: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_type: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=sa.text("'DRAFT'"),
        nullable=False,
    )
    source_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.knowledge_source_version.source_version_id"),
        nullable=True,
    )
    policy_payload: Mapped[dict] = mapped_column(
        JSONB,
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approved_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=True,
    )
