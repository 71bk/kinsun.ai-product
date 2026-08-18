"""add append-only memory confirmation evidence

Revision ID: f3b5d7e9a012
Revises: e2a4c6b8d901
Create Date: 2026-08-18 14:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3b5d7e9a012"
down_revision: str | Sequence[str] | None = "e2a4c6b8d901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.create_table(
        "memory_confirmation",
        sa.Column(
            "memory_confirmation_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.func.gen_random_uuid(),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("elder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_version", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("consent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_version", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column(
            "decision_support_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Reserved for the DecisionSupportProfile migration.",
        ),
        sa.Column("decision_support_profile_version", sa.Integer(), nullable=True),
        sa.Column("confirmation_method", sa.String(length=32), nullable=False),
        sa.Column("response_intent", sa.String(length=16), nullable=False),
        sa.Column("confirmed_by_actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confirmation_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("speaker_verification_level", sa.String(length=32), nullable=False),
        sa.Column("speaker_evidence_reference", sa.String(length=300), nullable=False),
        sa.Column("witness_actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("witness_evidence_reference", sa.String(length=300), nullable=True),
        sa.Column("confirmation_evidence_reference", sa.String(length=300), nullable=False),
        sa.Column("trace_id", sa.String(length=80), nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "memory_confirmation_id",
            name="pk_memory_confirmation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{SCHEMA}.tenant.tenant_id"],
            name="fk_memory_confirmation_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["elder_id"],
            [f"{SCHEMA}.elder.elder_id"],
            name="fk_memory_confirmation_elder",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["memory_id"],
            [f"{SCHEMA}.memory.memory_id"],
            name="fk_memory_confirmation_memory",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["consent_id"],
            [f"{SCHEMA}.consent_grant.consent_id"],
            name="fk_memory_confirmation_consent",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_actor_id"],
            [f"{SCHEMA}.actor.actor_id"],
            name="fk_memory_confirmation_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmation_session_id"],
            [f"{SCHEMA}.conversation_session.session_id"],
            name="fk_memory_confirmation_session",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["witness_actor_id"],
            [f"{SCHEMA}.actor.actor_id"],
            name="fk_memory_confirmation_witness",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "memory_id",
            "memory_version",
            "response_intent",
            name="uq_memory_confirmation_version_intent",
        ),
        sa.CheckConstraint(
            "memory_version > 0 AND consent_version > 0",
            name="ck_memory_confirmation_positive_versions",
        ),
        sa.CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$'",
            name="ck_memory_confirmation_content_digest",
        ),
        sa.CheckConstraint(
            "confirmation_method IN ('ELDER_UI','ELDER_VOICE','WITNESSED_VOICE')",
            name="ck_memory_confirmation_method",
        ),
        sa.CheckConstraint(
            "response_intent IN ('AFFIRM','REJECT','UNCERTAIN','DEFER')",
            name="ck_memory_confirmation_response_intent",
        ),
        sa.CheckConstraint(
            "speaker_verification_level IN ('VERIFIED_ELDER','WITNESSED_ELDER')",
            name="ck_memory_confirmation_speaker_level",
        ),
        sa.CheckConstraint(
            "(decision_support_profile_id IS NULL) = "
            "(decision_support_profile_version IS NULL) AND "
            "(decision_support_profile_version IS NULL OR decision_support_profile_version > 0)",
            name="ck_memory_confirmation_profile_binding",
        ),
        sa.CheckConstraint(
            "(witness_actor_id IS NULL) = (witness_evidence_reference IS NULL)",
            name="ck_memory_confirmation_witness_pair",
        ),
        sa.CheckConstraint(
            "confirmation_method <> 'WITNESSED_VOICE' OR witness_actor_id IS NOT NULL",
            name="ck_memory_confirmation_witnessed_method",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_memory_confirmation_trust_lookup",
        "memory_confirmation",
        [
            "memory_id",
            "memory_version",
            "content_digest",
            "policy_version",
            "response_intent",
        ],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_memory_confirmation_tenant_elder",
        "memory_confirmation",
        ["tenant_id", "elder_id", "confirmed_at"],
        schema=SCHEMA,
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_memory_confirmation_append_only
        BEFORE UPDATE OR DELETE ON {SCHEMA}.memory_confirmation
        FOR EACH ROW
        EXECUTE FUNCTION {SCHEMA}.prevent_update_delete()
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM {SCHEMA}.memory_confirmation) THEN
            RAISE EXCEPTION 'cannot remove append-only memory confirmation evidence';
          END IF;
        END
        $$;
        """
    )
    op.execute(
        f"DROP TRIGGER trg_memory_confirmation_append_only " f"ON {SCHEMA}.memory_confirmation"
    )
    op.drop_index(
        "ix_memory_confirmation_tenant_elder",
        table_name="memory_confirmation",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_memory_confirmation_trust_lookup",
        table_name="memory_confirmation",
        schema=SCHEMA,
    )
    op.drop_table("memory_confirmation", schema=SCHEMA)
