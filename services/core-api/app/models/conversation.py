"""Conversation session ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, BaseModel, TenantScopedMixin, pg_enum

LANGUAGE_CODE_ENUM = pg_enum(
    "language_code_enum",
    "ZH_TW",
    "NAN_TW",
    "HAK_TW",
    "EN_US",
    "MIXED",
    "UNKNOWN",
)


class ConversationSession(BaseModel, TenantScopedMixin):
    """One traceable voice-first interaction with a consent snapshot."""

    __tablename__ = "conversation_session"
    __pk_name__ = "session_id"

    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    initiator_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
        nullable=True,
    )
    initiator_type: Mapped[str] = mapped_column(String(24), nullable=False)
    language_route: Mapped[str] = mapped_column(LANGUAGE_CODE_ENUM, nullable=False)
    state: Mapped[str] = mapped_column(
        String(24),
        server_default=sa.text("'CREATED'"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    consent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.consent_grant.consent_id"),
        nullable=False,
    )
    consent_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str | None] = mapped_column(String(80))
