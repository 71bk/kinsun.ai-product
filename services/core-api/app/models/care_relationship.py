"""CareRelationship ORM model.

Represents a long-lived relationship between an Actor and an Elder,
optionally scoped to a CareUnit. Used for authorization decisions —
an actor needs an active relationship (or assignment) to access elder data.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin, pg_enum

#: eldercare_ai.relationship_type_enum
RELATIONSHIP_TYPE_ENUM = pg_enum(
    "relationship_type_enum",
    "DAYCARE_ASSIGNMENT",
    "HOME_CARE_ASSIGNMENT",
    "FAMILY_SHARE",
    "LEGAL_REPRESENTATIVE",
)


class CareRelationship(BaseModel, TenantScopedMixin):
    """Long-lived care relationship: Actor ↔ Elder.

    Inherits from BaseModel (id mapped onto relationship_id, created_at,
    updated_at) and TenantScopedMixin (tenant_id).

    A CareRelationship defines *who* can access *which* elder and
    under what scope. The relationship_type determines the nature
    of the link (daycare assignment, family share, legal representative).

    `scope` is JSONB. The policy layer treats it as a list of action strings,
    e.g. ["elder:basic:read"]. The column's server default is '{}' (an empty
    JSON object), which fails closed: no action is ever a member of it.
    """

    __tablename__ = "care_relationship"
    __pk_name__ = "relationship_id"

    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
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
    relationship_type: Mapped[str] = mapped_column(
        RELATIONSHIP_TYPE_ENUM,
        nullable=False,
    )
    scope: Mapped[list] = mapped_column(
        JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=sa.text("'ACTIVE'"),
        nullable=False,
    )
    # The baseline declares DEFAULT now(). Without the matching claim here
    # SQLAlchemy sends an explicit NULL for an unset attribute instead of
    # omitting the column, so the database default would never apply.
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
