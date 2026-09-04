"""add review-gated care action candidates

Revision ID: d1f3a5c7e9b0
Revises: b8d0f2a4c6e7
Create Date: 2026-09-04 14:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d1f3a5c7e9b0"
down_revision: str | Sequence[str] | None = "b8d0f2a4c6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.add_column(
        "care_event_version",
        sa.Column(
            "care_action_candidate_proposal",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "care_action_candidate",
        sa.Column(
            "care_action_candidate_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "elder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.elder.elder_id"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("suggested_title", sa.String(length=200), nullable=False),
        sa.Column("trigger_reason", sa.Text(), nullable=False),
        sa.Column("suggested_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="MEDIUM"),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="PENDING_REVIEW",
        ),
        sa.Column("disposition_reason_code", sa.String(length=120), nullable=True),
        sa.Column("disposition_notes", sa.Text(), nullable=True),
        sa.Column(
            "decided_by_actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.actor.actor_id"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "adopted_care_action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.care_action.care_action_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("extractor_version", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
            "action_type IN ('CONTACT_ELDER','CONTACT_FAMILY','CONFIRM_INFORMATION',"
            "'INVITE_ACTIVITY','FOLLOW_UP','OTHER')",
            name="ck_care_action_candidate_action_type",
        ),
        sa.CheckConstraint(
            "priority IN ('LOW','MEDIUM')",
            name="ck_care_action_candidate_priority",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW','ADOPTED','REJECTED','EXCLUDED')",
            name="ck_care_action_candidate_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_care_action_candidate_version"),
        sa.CheckConstraint(
            "(status = 'PENDING_REVIEW' AND decided_by_actor_id IS NULL "
            "AND decided_at IS NULL AND disposition_reason_code IS NULL "
            "AND disposition_notes IS NULL AND adopted_care_action_id IS NULL) OR "
            "(status = 'ADOPTED' AND decided_by_actor_id IS NOT NULL "
            "AND decided_at IS NOT NULL AND disposition_reason_code IS NOT NULL "
            "AND adopted_care_action_id IS NOT NULL) OR "
            "(status IN ('REJECTED','EXCLUDED') AND decided_by_actor_id IS NOT NULL "
            "AND decided_at IS NOT NULL AND disposition_reason_code IS NOT NULL "
            "AND adopted_care_action_id IS NULL)",
            name="ck_care_action_candidate_disposition",
        ),
        sa.UniqueConstraint(
            "adopted_care_action_id",
            name="uq_care_action_candidate_adopted_action",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_care_action_candidate_elder_status_created",
        "care_action_candidate",
        ["tenant_id", "elder_id", "status", sa.text("created_at DESC")],
        schema=SCHEMA,
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_care_action_candidate_set_updated_at
        BEFORE UPDATE ON {SCHEMA}.care_action_candidate
        FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.set_updated_at();
        """
    )

    op.create_table(
        "care_action_candidate_event_provenance",
        sa.Column(
            "care_action_candidate_event_provenance_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "care_action_candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                f"{SCHEMA}.care_action_candidate.care_action_candidate_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_status", sa.String(length=24), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("snapshot_schema_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "source_order BETWEEN 0 AND 15",
            name="ck_care_action_candidate_provenance_order",
        ),
        sa.CheckConstraint(
            "event_version >= 1",
            name="ck_care_action_candidate_provenance_version",
        ),
        sa.CheckConstraint(
            "source_status IN ('VERIFIED','CORRECTED')",
            name="ck_care_action_candidate_provenance_status",
        ),
        sa.CheckConstraint(
            "snapshot_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_care_action_candidate_provenance_sha256",
        ),
        sa.CheckConstraint(
            "snapshot_schema_version = 'care-event-provenance.v1'",
            name="ck_care_action_candidate_provenance_schema",
        ),
        sa.ForeignKeyConstraint(
            ["event_version_id", "event_id", "event_version"],
            [
                f"{SCHEMA}.care_event_version.event_version_id",
                f"{SCHEMA}.care_event_version.event_id",
                f"{SCHEMA}.care_event_version.version",
            ],
            name="fk_care_action_candidate_provenance_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "care_action_candidate_id",
            "source_order",
            name="uq_care_action_candidate_provenance_order",
        ),
        sa.UniqueConstraint(
            "care_action_candidate_id",
            "event_id",
            name="uq_care_action_candidate_provenance_event",
        ),
        sa.UniqueConstraint(
            "care_action_candidate_id",
            "event_version_id",
            name="uq_care_action_candidate_provenance_event_version",
        ),
        schema=SCHEMA,
    )

    op.execute(
        f"""
        CREATE FUNCTION {SCHEMA}.prevent_care_action_candidate_source_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'care action candidate source provenance is immutable';
        END;
        $$;

        CREATE TRIGGER trg_care_action_candidate_source_immutable
        BEFORE UPDATE OR DELETE ON {SCHEMA}.care_action_candidate_event_provenance
        FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.prevent_care_action_candidate_source_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM {SCHEMA}.care_action_candidate) OR EXISTS (
            SELECT 1 FROM {SCHEMA}.care_event_version
            WHERE care_action_candidate_proposal IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'cannot remove care action candidate schema while data exists';
          END IF;
        END
        $$;
        """
    )
    op.execute(
        f"DROP TRIGGER IF EXISTS trg_care_action_candidate_source_immutable "
        f"ON {SCHEMA}.care_action_candidate_event_provenance"
    )
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.prevent_care_action_candidate_source_mutation()")
    op.drop_table("care_action_candidate_event_provenance", schema=SCHEMA)
    op.execute(
        f"DROP TRIGGER IF EXISTS trg_care_action_candidate_set_updated_at "
        f"ON {SCHEMA}.care_action_candidate"
    )
    op.drop_index(
        "ix_care_action_candidate_elder_status_created",
        table_name="care_action_candidate",
        schema=SCHEMA,
    )
    op.drop_table("care_action_candidate", schema=SCHEMA)
    op.drop_column("care_event_version", "care_action_candidate_proposal", schema=SCHEMA)
