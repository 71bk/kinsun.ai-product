"""add assisted-tablet acknowledgement provenance to consent grants

Revision ID: b8c2d4e5f607
Revises: f7a9b1c3d456
Create Date: 2026-09-01 14:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b8c2d4e5f607"
down_revision: str | Sequence[str] | None = "f7a9b1c3d456"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.add_column(
        "consent_grant",
        sa.Column(
            "confirmation_method",
            sa.String(length=48),
            nullable=False,
            server_default=sa.text("'ACTOR_CONFIRMATION'"),
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "consent_grant",
        sa.Column(
            "recorded_by_actor_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "consent_grant",
        sa.Column(
            "assisted_session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.execute(
        sa.text(
            f"UPDATE {SCHEMA}.consent_grant "
            "SET recorded_by_actor_id = granted_by_actor_id "
            "WHERE recorded_by_actor_id IS NULL"
        )
    )
    op.alter_column(
        "consent_grant",
        "granted_by_actor_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_consent_recorded_by_actor",
        "consent_grant",
        "actor",
        ["recorded_by_actor_id"],
        ["actor_id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_consent_assisted_session",
        "consent_grant",
        "assisted_elder_session",
        ["assisted_session_id"],
        ["assisted_session_id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_consent_confirmation_provenance",
        "consent_grant",
        "(confirmation_method = 'ACTOR_CONFIRMATION' "
        "AND granted_by_actor_id IS NOT NULL "
        "AND assisted_session_id IS NULL) OR "
        "(confirmation_method = 'ASSISTED_TABLET_ACKNOWLEDGEMENT' "
        "AND granted_by_actor_id IS NULL "
        "AND recorded_by_actor_id IS NOT NULL "
        "AND assisted_session_id IS NOT NULL)",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_consent_assisted_session",
        "consent_grant",
        ["assisted_session_id", "purpose_code", "status"],
        schema=SCHEMA,
        unique=False,
    )


def downgrade() -> None:
    # Preserve the assisted acknowledgement provenance in the existing JSON
    # scope before restoring the legacy non-null actor column.
    op.execute(
        sa.text(
            f"UPDATE {SCHEMA}.consent_grant "
            "SET scope = scope || jsonb_build_object("
            "'downgraded_confirmation_method', confirmation_method, "
            "'downgraded_assisted_session_id', assisted_session_id::text), "
            "granted_by_actor_id = recorded_by_actor_id, "
            "confirmation_method = 'ACTOR_CONFIRMATION', "
            "assisted_session_id = NULL "
            "WHERE granted_by_actor_id IS NULL"
        )
    )
    op.drop_index(
        "ix_consent_assisted_session",
        table_name="consent_grant",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_consent_confirmation_provenance",
        "consent_grant",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "fk_consent_assisted_session",
        "consent_grant",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_consent_recorded_by_actor",
        "consent_grant",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.alter_column(
        "consent_grant",
        "granted_by_actor_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
        schema=SCHEMA,
    )
    op.drop_column("consent_grant", "assisted_session_id", schema=SCHEMA)
    op.drop_column("consent_grant", "recorded_by_actor_id", schema=SCHEMA)
    op.drop_column("consent_grant", "confirmation_method", schema=SCHEMA)
