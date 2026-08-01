"""Agent run and audited tool-call ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import SCHEMA_NAME, Base


class AgentRun(Base):
    __tablename__ = "agent_run"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.conversation_session.session_id"),
    )
    elder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.elder.elder_id"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.tenant.tenant_id"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
    )
    parent_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.agent_run.agent_run_id"),
    )
    agent_id: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    result_status: Mapped[str] = mapped_column(String(32), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    policy_version: Mapped[str | None] = mapped_column(String(80))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage: Mapped[dict] = mapped_column(
        JSONB,
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )
    stop_reason: Mapped[str | None] = mapped_column(String(160))
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


class AgentToolCall(Base):
    __tablename__ = "agent_tool_call"

    tool_call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.func.gen_random_uuid(),
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.agent_run.agent_run_id"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA_NAME}.actor.actor_id"),
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(160),
        ForeignKey(f"{SCHEMA_NAME}.idempotency_record.idempotency_key"),
    )
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(40), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_status: Mapped[str] = mapped_column(String(24), nullable=False)
    response_payload: Mapped[dict | None] = mapped_column(JSONB)
    reason_code: Mapped[str | None] = mapped_column(String(120))
    retryable: Mapped[bool] = mapped_column(
        Boolean,
        server_default=sa.false(),
        nullable=False,
    )
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
