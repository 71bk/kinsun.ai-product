"""expand care-event speaker evidence lineage

Revision ID: e2a4c6b8d901
Revises: d9f1a7c3e520
Create Date: 2026-08-18 12:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e2a4c6b8d901"
down_revision: str | Sequence[str] | None = "d9f1a7c3e520"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    columns = (
        sa.Column("speaker_role", sa.String(length=32), nullable=True),
        sa.Column("speaker_actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("speaker_verification_level", sa.String(length=32), nullable=True),
        sa.Column("speaker_verification_method", sa.String(length=48), nullable=True),
        sa.Column("speaker_evidence_reference", sa.String(length=300), nullable=True),
    )
    for column in columns:
        op.add_column("care_event_version", column, schema=SCHEMA)

    op.create_foreign_key(
        "fk_care_event_version_speaker_actor",
        "care_event_version",
        "actor",
        ["speaker_actor_id"],
        ["actor_id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_care_event_version_speaker_level",
        "care_event_version",
        "speaker_verification_level IS NULL OR speaker_verification_level IN ("
        "'UNKNOWN','VERIFIED_ELDER','WITNESSED_ELDER','THIRD_PARTY')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_care_event_version_verified_speaker_evidence",
        "care_event_version",
        "speaker_verification_level NOT IN ('VERIFIED_ELDER','WITNESSED_ELDER') "
        "OR (speaker_actor_id IS NOT NULL AND speaker_evidence_reference IS NOT NULL "
        "AND speaker_verification_method IS NOT NULL)",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM {SCHEMA}.care_event_version
            WHERE speaker_role IS NOT NULL
               OR speaker_actor_id IS NOT NULL
               OR speaker_verification_level IS NOT NULL
               OR speaker_verification_method IS NOT NULL
               OR speaker_evidence_reference IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'cannot remove care-event speaker evidence while data exists';
          END IF;
        END
        $$;
        """
    )
    op.drop_constraint(
        "ck_care_event_version_verified_speaker_evidence",
        "care_event_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_care_event_version_speaker_level",
        "care_event_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "fk_care_event_version_speaker_actor",
        "care_event_version",
        schema=SCHEMA,
        type_="foreignkey",
    )
    for name in (
        "speaker_evidence_reference",
        "speaker_verification_method",
        "speaker_verification_level",
        "speaker_actor_id",
        "speaker_role",
    ):
        op.drop_column("care_event_version", name, schema=SCHEMA)
