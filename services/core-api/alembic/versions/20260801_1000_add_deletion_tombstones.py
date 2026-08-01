"""add replay-safe deletion tombstones and processing metadata

Revision ID: d3b7e2a4f901
Revises: a7c34d91e6f2
Create Date: 2026-08-01 10:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d3b7e2a4f901"
down_revision: str | Sequence[str] | None = "a7c34d91e6f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def _install_deletion_scrub_guard() -> None:
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION eldercare_ai.protect_memory_version_content()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.memory_id IS DISTINCT FROM OLD.memory_id
                   OR NEW.version IS DISTINCT FROM OLD.version
                   OR NEW.valid_from IS DISTINCT FROM OLD.valid_from
                   OR NEW.created_by_actor_id IS DISTINCT FROM OLD.created_by_actor_id
                   OR NEW.supersedes_version_id IS DISTINCT FROM OLD.supersedes_version_id
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at
                THEN
                    RAISE EXCEPTION
                        'Memory version identity is immutable; create a new version instead';
                END IF;

                IF (NEW.content IS DISTINCT FROM OLD.content
                    OR NEW.source_event_ids IS DISTINCT FROM OLD.source_event_ids)
                   AND NOT (
                       NEW.version_status = 'DELETED'
                       AND NEW.content = ''
                       AND NEW.source_event_ids = '{}'::uuid[]
                   )
                THEN
                    RAISE EXCEPTION
                        'Memory version content is immutable except for approved deletion scrub';
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            "COMMENT ON FUNCTION eldercare_ai.protect_memory_version_content() IS "
            "'禁止覆蓋記憶版本；僅允許刪除流程清空內容與來源並轉為 DELETED。'"
        )
    )


def _restore_original_memory_guard() -> None:
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION eldercare_ai.protect_memory_version_content()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.memory_id IS DISTINCT FROM OLD.memory_id
                   OR NEW.version IS DISTINCT FROM OLD.version
                   OR NEW.content IS DISTINCT FROM OLD.content
                   OR NEW.source_event_ids IS DISTINCT FROM OLD.source_event_ids
                   OR NEW.valid_from IS DISTINCT FROM OLD.valid_from
                   OR NEW.created_by_actor_id IS DISTINCT FROM OLD.created_by_actor_id
                   OR NEW.supersedes_version_id IS DISTINCT FROM OLD.supersedes_version_id
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at
                THEN
                    RAISE EXCEPTION '%',
                        'Memory version content is immutable; only version_status '
                        || 'and valid_to may change';
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            "COMMENT ON FUNCTION eldercare_ai.protect_memory_version_content() IS "
            "'允許停用舊記憶版本，但禁止覆蓋版本內容與來源。'"
        )
    )


def upgrade() -> None:
    op.add_column(
        "deletion_request",
        sa.Column("policy_version", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "deletion_request",
        sa.Column(
            "legal_hold_status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'NOT_EVALUATED'"),
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "deletion_request",
        sa.Column("retention_basis", sa.String(length=120), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_deletion_request_legal_hold_status",
        "deletion_request",
        "legal_hold_status IN ('NOT_EVALUATED','CLEAR','ACTIVE','RELEASED')",
        schema=SCHEMA,
    )

    op.add_column(
        "deletion_job_item",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "deletion_job_item",
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "deletion_job_item",
        sa.Column("verification_code", sa.String(length=120), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "deletion_tombstone",
        sa.Column(
            "deletion_tombstone_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("elder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deletion_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_ref_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=120), nullable=False),
        sa.Column("retention_basis", sa.String(length=120), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "subject_ref_hash ~ '^[0-9a-f]{64}$'",
            name="ck_deletion_tombstone_subject_hash",
        ),
        sa.CheckConstraint(
            "resource_id_hash ~ '^[0-9a-f]{64}$'",
            name="ck_deletion_tombstone_resource_hash",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{SCHEMA}.tenant.tenant_id"],
            name="fk_deletion_tombstone_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["elder_id"],
            [f"{SCHEMA}.elder.elder_id"],
            name="fk_deletion_tombstone_elder",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deletion_request_id"],
            [f"{SCHEMA}.deletion_request.deletion_request_id"],
            name="fk_deletion_tombstone_request",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "deletion_tombstone_id",
            name="pk_deletion_tombstone",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "resource_type",
            "resource_id_hash",
            name="uq_deletion_tombstone_resource",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_deletion_tombstone_subject_resource",
        "deletion_tombstone",
        ["tenant_id", "subject_ref_hash", "resource_type"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_deletion_request_elder_status",
        "deletion_request",
        ["elder_id", "status"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_deletion_job_item_request_status",
        "deletion_job_item",
        ["deletion_request_id", "status"],
        unique=False,
        schema=SCHEMA,
    )
    op.execute(
        sa.text(
            f"CREATE UNIQUE INDEX uq_deletion_request_consent_id "
            f"ON {SCHEMA}.deletion_request (consent_id) WHERE consent_id IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            f"CREATE UNIQUE INDEX uq_deletion_job_item_target "
            f"ON {SCHEMA}.deletion_job_item "
            "(deletion_request_id, resource_type, system_of_record, "
            "COALESCE(resource_id, '00000000-0000-0000-0000-000000000000'::uuid))"
        )
    )
    _install_deletion_scrub_guard()


def downgrade() -> None:
    _restore_original_memory_guard()
    op.execute(sa.text(f"DROP INDEX IF EXISTS {SCHEMA}.uq_deletion_job_item_target"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS {SCHEMA}.uq_deletion_request_consent_id"))
    op.drop_index(
        "ix_deletion_job_item_request_status",
        table_name="deletion_job_item",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_deletion_request_elder_status",
        table_name="deletion_request",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_deletion_tombstone_subject_resource",
        table_name="deletion_tombstone",
        schema=SCHEMA,
    )
    op.drop_table("deletion_tombstone", schema=SCHEMA)

    op.drop_column("deletion_job_item", "verification_code", schema=SCHEMA)
    op.drop_column("deletion_job_item", "failure_code", schema=SCHEMA)
    op.drop_column("deletion_job_item", "started_at", schema=SCHEMA)

    op.drop_constraint(
        "ck_deletion_request_legal_hold_status",
        "deletion_request",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_column("deletion_request", "retention_basis", schema=SCHEMA)
    op.drop_column("deletion_request", "legal_hold_status", schema=SCHEMA)
    op.drop_column("deletion_request", "policy_version", schema=SCHEMA)
