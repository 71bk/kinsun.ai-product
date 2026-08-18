"""add versioned decision support profile gate

Revision ID: a4c6e8f0b123
Revises: f3b5d7e9a012
Create Date: 2026-08-18 17:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a4c6e8f0b123"
down_revision: str | Sequence[str] | None = "f3b5d7e9a012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.create_table(
        "decision_support_profile",
        sa.Column(
            "decision_support_profile_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.func.gen_random_uuid(),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("elder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_scope", sa.String(length=48), nullable=False),
        sa.Column("data_class", sa.String(length=48), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column(
            "allowed_memory_risks",
            postgresql.ARRAY(sa.String(length=16)),
            server_default=sa.text("ARRAY['LOW','MEDIUM']::varchar[]"),
            nullable=False,
        ),
        sa.Column("basis_reference", sa.String(length=300), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("supersedes_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "decision_support_profile_id",
            name="pk_decision_support_profile",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{SCHEMA}.tenant.tenant_id"],
            name="fk_decision_support_profile_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["elder_id"],
            [f"{SCHEMA}.elder.elder_id"],
            name="fk_decision_support_profile_elder",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_actor_id"],
            [f"{SCHEMA}.actor.actor_id"],
            name="fk_decision_support_profile_reviewer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_profile_id"],
            [f"{SCHEMA}.decision_support_profile.decision_support_profile_id"],
            name="fk_decision_support_profile_supersedes",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "decision_scope = 'MEMORY_CONFIRMATION'",
            name="ck_decision_support_profile_scope",
        ),
        sa.CheckConstraint(
            "data_class IN ('ALL_MEMORY','PREFERENCE','IMPORTANT_RELATIONSHIP',"
            "'ROUTINE','COMMUNICATION_PREFERENCE','PERSONAL_HISTORY')",
            name="ck_decision_support_profile_data_class",
        ),
        sa.CheckConstraint(
            "mode IN ('STANDARD','SUPPORTED','REPRESENTATIVE_REQUIRED')",
            name="ck_decision_support_profile_mode",
        ),
        sa.CheckConstraint(
            "profile_version > 0",
            name="ck_decision_support_profile_version",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at > effective_from",
            name="ck_decision_support_profile_effective_window",
        ),
        sa.CheckConstraint(
            "allowed_memory_risks <@ ARRAY['LOW','MEDIUM']::varchar[]",
            name="ck_decision_support_profile_allowed_risks",
        ),
        sa.CheckConstraint(
            "mode <> 'REPRESENTATIVE_REQUIRED' OR cardinality(allowed_memory_risks) = 0",
            name="ck_decision_support_profile_representative_risks",
        ),
        sa.CheckConstraint(
            "supersedes_profile_id IS NULL OR "
            "supersedes_profile_id <> decision_support_profile_id",
            name="ck_decision_support_profile_not_self_superseding",
        ),
        sa.UniqueConstraint(
            "decision_support_profile_id",
            "profile_version",
            name="uq_decision_support_profile_id_version",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "elder_id",
            "decision_scope",
            "data_class",
            "profile_version",
            name="uq_decision_support_profile_scope_version",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_decision_support_profile_resolution",
        "decision_support_profile",
        ["tenant_id", "elder_id", "decision_scope", "data_class", "profile_version"],
        schema=SCHEMA,
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_decision_support_profile_append_only
        BEFORE UPDATE OR DELETE ON {SCHEMA}.decision_support_profile
        FOR EACH ROW
        EXECUTE FUNCTION {SCHEMA}.prevent_update_delete()
        """
    )

    op.add_column(
        "memory",
        sa.Column("decision_support_profile_id", postgresql.UUID(as_uuid=True)),
        schema=SCHEMA,
    )
    op.add_column(
        "memory",
        sa.Column("decision_support_profile_version", sa.Integer()),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_memory_decision_support_profile_binding",
        "memory",
        "(decision_support_profile_id IS NULL) = "
        "(decision_support_profile_version IS NULL) AND "
        "(decision_support_profile_version IS NULL OR decision_support_profile_version > 0)",
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_memory_decision_support_profile",
        "memory",
        "decision_support_profile",
        ["decision_support_profile_id", "decision_support_profile_version"],
        ["decision_support_profile_id", "profile_version"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_memory_confirmation_decision_support_profile",
        "memory_confirmation",
        "decision_support_profile",
        ["decision_support_profile_id", "decision_support_profile_version"],
        ["decision_support_profile_id", "profile_version"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM {SCHEMA}.decision_support_profile)
             OR EXISTS (
                SELECT 1 FROM {SCHEMA}.memory
                WHERE decision_support_profile_id IS NOT NULL
             )
             OR EXISTS (
                SELECT 1 FROM {SCHEMA}.memory_confirmation
                WHERE decision_support_profile_id IS NOT NULL
             ) THEN
            RAISE EXCEPTION 'cannot remove decision support profile evidence';
          END IF;
        END
        $$;
        """
    )
    op.drop_constraint(
        "fk_memory_confirmation_decision_support_profile",
        "memory_confirmation",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_memory_decision_support_profile",
        "memory",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_memory_decision_support_profile_binding",
        "memory",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_column("memory", "decision_support_profile_version", schema=SCHEMA)
    op.drop_column("memory", "decision_support_profile_id", schema=SCHEMA)
    op.execute(
        f"DROP TRIGGER trg_decision_support_profile_append_only "
        f"ON {SCHEMA}.decision_support_profile"
    )
    op.drop_index(
        "ix_decision_support_profile_resolution",
        table_name="decision_support_profile",
        schema=SCHEMA,
    )
    op.drop_table("decision_support_profile", schema=SCHEMA)
