"""add immutable Care Action source-event provenance

Revision ID: a7c9e1f3b5d6
Revises: f3a5b7c9d024
Create Date: 2026-09-03 14:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c9e1f3b5d6"
down_revision: str | Sequence[str] | None = "f3a5b7c9d024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_care_event_version_identity",
        "care_event_version",
        ["event_version_id", "event_id", "version"],
        schema=SCHEMA,
    )
    op.create_table(
        "care_action_event_provenance",
        sa.Column(
            "care_action_event_provenance_id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("care_action_id", sa.UUID(), nullable=False),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("event_version_id", sa.UUID(), nullable=False),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "source_order BETWEEN 0 AND 15",
            name="ck_care_action_event_provenance_order",
        ),
        sa.CheckConstraint(
            "event_version >= 1",
            name="ck_care_action_event_provenance_version",
        ),
        sa.CheckConstraint(
            "source_status IN ('VERIFIED','CORRECTED')",
            name="ck_care_action_event_provenance_status",
        ),
        sa.CheckConstraint(
            "snapshot_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_care_action_event_provenance_sha256",
        ),
        sa.CheckConstraint(
            "snapshot_schema_version = 'care-event-provenance.v1'",
            name="ck_care_action_event_provenance_schema",
        ),
        sa.ForeignKeyConstraint(
            ["care_action_id"],
            [f"{SCHEMA}.care_action.care_action_id"],
            name="fk_care_action_event_provenance_action",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_version_id", "event_id", "event_version"],
            [
                f"{SCHEMA}.care_event_version.event_version_id",
                f"{SCHEMA}.care_event_version.event_id",
                f"{SCHEMA}.care_event_version.version",
            ],
            name="fk_care_action_event_provenance_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "care_action_event_provenance_id",
            name="pk_care_action_event_provenance",
        ),
        sa.UniqueConstraint(
            "care_action_id",
            "source_order",
            name="uq_care_action_event_provenance_order",
        ),
        sa.UniqueConstraint(
            "care_action_id",
            "event_id",
            name="uq_care_action_event_provenance_event",
        ),
        schema=SCHEMA,
    )
    op.execute(
        sa.text(
            f"COMMENT ON TABLE {SCHEMA}.care_action_event_provenance IS "
            "'Append-only binding to the exact formal Care Event versions "
            "used to create a Care Action'"
        )
    )
    op.execute(
        sa.text(
            f"COMMENT ON COLUMN {SCHEMA}.care_action_event_provenance.snapshot_sha256 IS "
            "'Lowercase SHA-256 of the canonical source snapshot named by snapshot_schema_version'"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER trg_care_action_event_provenance_immutable "
            f"BEFORE UPDATE OR DELETE ON {SCHEMA}.care_action_event_provenance "
            f"FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.prevent_update_delete()"
        )
    )
    op.execute(
        sa.text(
            f"CREATE FUNCTION {SCHEMA}.prevent_care_action_source_rebinding() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN "
            "IF NEW.related_event_ids IS DISTINCT FROM OLD.related_event_ids THEN "
            "RAISE EXCEPTION 'Care Action source-event bindings are immutable'; "
            "END IF; "
            "RETURN NEW; "
            "END; $$"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER trg_care_action_source_binding_immutable "
            f"BEFORE UPDATE OF related_event_ids ON {SCHEMA}.care_action "
            f"FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.prevent_care_action_source_rebinding()"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"DROP TRIGGER IF EXISTS trg_care_action_source_binding_immutable "
            f"ON {SCHEMA}.care_action"
        )
    )
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {SCHEMA}.prevent_care_action_source_rebinding()"))
    op.drop_table("care_action_event_provenance", schema=SCHEMA)
    op.drop_constraint(
        "uq_care_event_version_identity",
        "care_event_version",
        schema=SCHEMA,
        type_="unique",
    )
