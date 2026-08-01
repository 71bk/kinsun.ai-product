"""ASR transcript version ORM model.

Transcript contents are restricted data.  This model is persistence-only:
callers must recheck TRANSCRIPT_STORAGE consent before any read or write.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base
from app.models.conversation import LANGUAGE_CODE_ENUM


class TranscriptVersion(Base):
    """Immutable ASR transcript version linked to one conversation session."""

    __tablename__ = "transcript_version"

    transcript_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.conversation_session.session_id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str] = mapped_column(LANGUAGE_CODE_ENUM, nullable=False)
    asr_model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    confirmation_status: Mapped[str] = mapped_column(
        String(24),
        server_default=sa.text("'UNCONFIRMED'"),
        nullable=False,
    )
    supersedes_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.transcript_version.transcript_version_id"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
