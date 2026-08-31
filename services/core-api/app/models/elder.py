"""Elder ORM model.

Represents an elder (primary care recipient) within a tenant.
Authorization-relevant care unit association is established via
CareRelationship; primary_care_unit_id here is only the elder's home unit.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin, pg_enum

#: eldercare_ai.language_code_enum
LANGUAGE_CODE_ENUM = pg_enum(
    "language_code_enum",
    "ZH_TW",
    "NAN_TW",
    "HAK_TW",
    "EN_US",
    "MIXED",
    "UNKNOWN",
)


class Elder(BaseModel, TenantScopedMixin):
    """Elder belongs to exactly one Tenant.

    Inherits from BaseModel (id mapped onto elder_id, created_at, updated_at)
    and TenantScopedMixin (tenant_id).

    Authorization never reads primary_care_unit_id — it goes through
    CareRelationship.care_unit_id. This column only records the elder's
    home unit for display.
    """

    __tablename__ = "elder"
    __pk_name__ = "elder_id"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=True,
        unique=True,
    )
    primary_care_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.care_unit.care_unit_id"),
        nullable=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )
    # No server_default: the baseline declares this NOT NULL with no DEFAULT,
    # so the caller must state the care setting. Claiming a default here would
    # make SQLAlchemy omit the column and let PostgreSQL reject the INSERT.
    primary_care_setting: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=sa.text("'ACTIVE'"),
        nullable=False,
    )
    preferred_language: Mapped[str] = mapped_column(
        LANGUAGE_CODE_ENUM,
        server_default=sa.text("'ZH_TW'"),
        nullable=False,
    )
    preferred_name: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    response_length_preference: Mapped[str] = mapped_column(
        String(20),
        server_default=sa.text("'STANDARD'"),
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        server_default=sa.text("'Asia/Taipei'"),
        nullable=False,
    )
