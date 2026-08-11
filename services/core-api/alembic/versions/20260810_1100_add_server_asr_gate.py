"""add server-side ASR gate and session input mode

Revision ID: 4f8a2c1d9e60
Revises: 6e1f9a3c7d42
Create Date: 2026-08-10 11:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4f8a2c1d9e60"
down_revision: str | Sequence[str] | None = "6e1f9a3c7d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.add_column(
        "conversation_session",
        sa.Column(
            "input_mode",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'text'"),
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_conversation_input_mode",
        "conversation_session",
        "input_mode IN ('text','voice','voice_with_text_fallback')",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "conversation_session_state_check",
        "conversation_session",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "conversation_session_state_check",
        "conversation_session",
        "state IN ('CREATED','RECORDING','AWAITING_CONFIRMATION','PROCESSING',"
        "'RESPONDING','COMPLETED','CANCELLED','FAILED')",
        schema=SCHEMA,
    )

    op.create_table(
        "asr_gate_evidence",
        sa.Column(
            "asr_gate_evidence_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.tenant.tenant_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{SCHEMA}.conversation_session.session_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "elder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.elder.elder_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "language_route",
            postgresql.ENUM(
                name="language_code_enum",
                schema=SCHEMA,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("asr_model_version", sa.String(length=160), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("gate_status", sa.String(length=32), nullable=False),
        sa.Column("transcript_digest", sa.String(length=64), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("confirmation_action", sa.String(length=16), nullable=True),
        sa.Column(
            "confirmed_by_actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.actor.actor_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_asr_gate_confidence",
        ),
        sa.CheckConstraint(
            "gate_status IN "
            "('ALLOWED','AWAITING_CONFIRMATION','CONFIRMED','REJECTED')",
            name="ck_asr_gate_status",
        ),
        sa.CheckConstraint(
            "transcript_digest ~ '^[0-9a-f]{64}$'",
            name="ck_asr_gate_transcript_digest",
        ),
        sa.CheckConstraint(
            "confirmation_action IS NULL OR "
            "confirmation_action IN ('CONFIRM','REJECT')",
            name="ck_asr_gate_confirmation_action",
        ),
        sa.CheckConstraint(
            "(gate_status IN ('ALLOWED','AWAITING_CONFIRMATION') "
            "AND confirmation_action IS NULL "
            "AND confirmed_by_actor_id IS NULL AND confirmed_at IS NULL) OR "
            "(gate_status = 'CONFIRMED' AND confirmation_action = 'CONFIRM' "
            "AND confirmed_by_actor_id IS NOT NULL AND confirmed_at IS NOT NULL) OR "
            "(gate_status = 'REJECTED' AND confirmation_action = 'REJECT' "
            "AND confirmed_by_actor_id IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="ck_asr_gate_confirmation_consistency",
        ),
        sa.UniqueConstraint("session_id", name="uq_asr_gate_evidence_session"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_asr_gate_evidence_tenant_elder",
        "asr_gate_evidence",
        ["tenant_id", "elder_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM eldercare_ai.conversation_session
            WHERE state = 'AWAITING_CONFIRMATION'
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade while AWAITING_CONFIRMATION sessions exist';
          END IF;
        END
        $$;
        """
    )
    op.drop_index(
        "ix_asr_gate_evidence_tenant_elder",
        table_name="asr_gate_evidence",
        schema=SCHEMA,
    )
    op.drop_table("asr_gate_evidence", schema=SCHEMA)

    op.drop_constraint(
        "conversation_session_state_check",
        "conversation_session",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "conversation_session_state_check",
        "conversation_session",
        "state IN ('CREATED','RECORDING','PROCESSING','RESPONDING',"
        "'COMPLETED','CANCELLED','FAILED')",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_conversation_input_mode",
        "conversation_session",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_column("conversation_session", "input_mode", schema=SCHEMA)
