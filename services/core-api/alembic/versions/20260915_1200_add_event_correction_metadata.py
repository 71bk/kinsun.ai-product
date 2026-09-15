"""Preserve event metadata before and after human correction without backfill.

Revision ID: f4b6d8e0a213
Revises: e3a5c7d9f102
"""

import sqlalchemy as sa
from alembic import op

revision = "f4b6d8e0a213"
down_revision = "e3a5c7d9f102"
branch_labels = None
depends_on = None
SCHEMA = "eldercare_ai"


def upgrade() -> None:
    for side in ("before", "after"):
        op.add_column(
            "review_decision", sa.Column(f"{side}_event_type", sa.String(64)), schema=SCHEMA
        )
        op.add_column(
            "review_decision",
            sa.Column(f"{side}_event_time", sa.DateTime(timezone=True)),
            schema=SCHEMA,
        )
    op.create_check_constraint(
        "ck_review_event_metadata_pair",
        "review_decision",
        "(before_event_type IS NULL AND after_event_type IS NULL "
        "AND before_event_time IS NULL AND after_event_time IS NULL) OR "
        "(before_event_type IS NOT NULL AND after_event_type IS NOT NULL "
        "AND target_type = 'CARE_EVENT' AND event_id IS NOT NULL AND decision = 'CORRECT')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("ck_review_event_metadata_pair", "review_decision", schema=SCHEMA)
    for side in ("after", "before"):
        op.drop_column("review_decision", f"{side}_event_time", schema=SCHEMA)
        op.drop_column("review_decision", f"{side}_event_type", schema=SCHEMA)
