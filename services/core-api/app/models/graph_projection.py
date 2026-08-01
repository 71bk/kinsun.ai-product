"""Graph projection delivery-state ORM model.

Aurora remains the source of truth.  This model records whether a rebuildable
projection has reached a graph backend; it never grants access by itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base


class GraphProjectionRecord(Base):
    """Projection progress for one immutable source version."""

    __tablename__ = "graph_projection_record"

    projection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    projection_status: Mapped[str] = mapped_column(
        String(20),
        server_default=sa.text("'PENDING'"),
        nullable=False,
    )
    graph_key: Mapped[str | None] = mapped_column(String(300))
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.outbox_event.outbox_event_id"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        server_default="0",
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )
