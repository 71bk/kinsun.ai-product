"""expand memory trust and version-binding evidence

Revision ID: d9f1a7c3e520
Revises: b8d0e4f6a213
Create Date: 2026-08-18 10:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9f1a7c3e520"
down_revision: str | Sequence[str] | None = "b8d0e4f6a213"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    memory_columns = (
        sa.Column("memory_kind", sa.String(length=48), nullable=True),
        sa.Column("actual_risk_level", sa.String(length=16), nullable=True),
        sa.Column("policy_decision", sa.String(length=40), nullable=True),
        sa.Column("policy_version", sa.String(length=80), nullable=True),
        sa.Column("verification_level", sa.String(length=32), nullable=True),
        sa.Column("required_verification", sa.String(length=32), nullable=True),
        sa.Column("speaker_verification_level", sa.String(length=32), nullable=True),
        sa.Column("speaker_evidence_reference", sa.String(length=300), nullable=True),
        sa.Column("confirmed_version", sa.Integer(), nullable=True),
        sa.Column("confirmed_content_digest", sa.String(length=64), nullable=True),
        sa.Column("lifecycle_reason", sa.String(length=120), nullable=True),
        sa.Column("consent_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    for column in memory_columns:
        op.add_column("memory", column, schema=SCHEMA)

    op.create_foreign_key(
        "fk_memory_consent_id",
        "memory",
        "consent_grant",
        ["consent_id"],
        ["consent_id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_memory_kind",
        "memory",
        "memory_kind IS NULL OR memory_kind IN ("
        "'MUSIC_PREFERENCE','HOBBY','PREFERRED_ADDRESS','FAMILY_RELATIONSHIP',"
        "'CONTACT_ROUTINE','DAILY_ROUTINE','HEALTH_INFERENCE','MEDICATION_JUDGMENT',"
        "'MOOD_OR_LONELINESS_INFERENCE','FAMILY_CONFLICT','FINANCIAL_INFORMATION',"
        "'SENSITIVE_OR_UNKNOWN')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_actual_risk_level",
        "memory",
        "actual_risk_level IS NULL OR actual_risk_level IN ('LOW','MEDIUM','HIGH')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_policy_decision",
        "memory",
        "policy_decision IS NULL OR policy_decision IN ("
        "'AUTO_ACTIVATED_LOW','PENDING_ELDER_CONFIRMATION',"
        "'ELDER_CONFIRMED_MEDIUM','REJECTED_HIGH_RISK','NO_MEMORY')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_verification_level",
        "memory",
        "verification_level IS NULL OR verification_level IN ("
        "'UNVERIFIED','POLICY_VERIFIED','ELDER_CONFIRMED')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_required_verification",
        "memory",
        "required_verification IS NULL OR required_verification IN ("
        "'NONE','ELDER_CONFIRMATION','RESTRICTED')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_speaker_verification_level",
        "memory",
        "speaker_verification_level IS NULL OR speaker_verification_level IN ("
        "'UNKNOWN','VERIFIED_ELDER','WITNESSED_ELDER','THIRD_PARTY')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_verified_speaker_evidence",
        "memory",
        "speaker_verification_level NOT IN ('VERIFIED_ELDER','WITNESSED_ELDER') "
        "OR speaker_evidence_reference IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_confirmed_version_positive",
        "memory",
        "confirmed_version IS NULL OR confirmed_version > 0",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_confirmation_binding",
        "memory",
        "(confirmed_version IS NULL) = (confirmed_content_digest IS NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_confirmed_content_digest",
        "memory",
        "confirmed_content_digest IS NULL OR confirmed_content_digest ~ '^[0-9a-f]{64}$'",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_memory_trusted_context",
        "memory",
        ["tenant_id", "elder_id", "status", "policy_version"],
        schema=SCHEMA,
    )

    op.add_column(
        "memory_version",
        sa.Column("content_digest", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "memory_version",
        sa.Column("source_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "memory_version",
        sa.Column("source_turn_reference", sa.String(length=160), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "memory_version",
        sa.Column("proposal_risk_hint", sa.String(length=16), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_memory_version_source_session",
        "memory_version",
        "conversation_session",
        ["source_session_id"],
        ["session_id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_memory_version_content_digest",
        "memory_version",
        "content_digest IS NULL OR content_digest ~ '^[0-9a-f]{64}$'",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_version_proposal_risk_hint",
        "memory_version",
        "proposal_risk_hint IS NULL OR proposal_risk_hint IN ('LOW','MEDIUM','HIGH')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM {SCHEMA}.memory
            WHERE memory_kind IS NOT NULL
               OR actual_risk_level IS NOT NULL
               OR policy_decision IS NOT NULL
               OR policy_version IS NOT NULL
               OR verification_level IS NOT NULL
               OR required_verification IS NOT NULL
               OR speaker_verification_level IS NOT NULL
               OR speaker_evidence_reference IS NOT NULL
               OR confirmed_version IS NOT NULL
               OR confirmed_content_digest IS NOT NULL
               OR lifecycle_reason IS NOT NULL
               OR consent_id IS NOT NULL
          ) OR EXISTS (
            SELECT 1 FROM {SCHEMA}.memory_version
            WHERE content_digest IS NOT NULL
               OR source_session_id IS NOT NULL
               OR source_turn_reference IS NOT NULL
               OR proposal_risk_hint IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'cannot remove memory trust evidence while data exists';
          END IF;
        END
        $$;
        """
    )

    op.drop_constraint(
        "ck_memory_version_proposal_risk_hint",
        "memory_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_memory_version_content_digest",
        "memory_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "fk_memory_version_source_session",
        "memory_version",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("memory_version", "proposal_risk_hint", schema=SCHEMA)
    op.drop_column("memory_version", "source_turn_reference", schema=SCHEMA)
    op.drop_column("memory_version", "source_session_id", schema=SCHEMA)
    op.drop_column("memory_version", "content_digest", schema=SCHEMA)

    op.drop_index("ix_memory_trusted_context", table_name="memory", schema=SCHEMA)
    for name in (
        "ck_memory_confirmed_content_digest",
        "ck_memory_confirmation_binding",
        "ck_memory_confirmed_version_positive",
        "ck_memory_verified_speaker_evidence",
        "ck_memory_speaker_verification_level",
        "ck_memory_required_verification",
        "ck_memory_verification_level",
        "ck_memory_policy_decision",
        "ck_memory_actual_risk_level",
        "ck_memory_kind",
    ):
        op.drop_constraint(name, "memory", schema=SCHEMA, type_="check")
    op.drop_constraint(
        "fk_memory_consent_id",
        "memory",
        schema=SCHEMA,
        type_="foreignkey",
    )
    for name in (
        "consent_id",
        "lifecycle_reason",
        "confirmed_content_digest",
        "confirmed_version",
        "speaker_evidence_reference",
        "speaker_verification_level",
        "required_verification",
        "verification_level",
        "policy_version",
        "policy_decision",
        "actual_risk_level",
        "memory_kind",
    ):
        op.drop_column("memory", name, schema=SCHEMA)
