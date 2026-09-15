"""Record explicit event provenance without guessing legacy manual sources.

Revision ID: a5c7e9f1b324
Revises: f4b6d8e0a213
"""

import sqlalchemy as sa
from alembic import op

revision = "a5c7e9f1b324"
down_revision = "f4b6d8e0a213"
branch_labels = None
depends_on = None
SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.add_column("care_event", sa.Column("source_type", sa.String(32)), schema=SCHEMA)
    op.create_check_constraint(
        "ck_care_event_source_type",
        "care_event",
        "source_type IS NULL OR "
        "(source_type = 'MANUAL' AND source_session_id IS NULL) OR "
        "(source_type = 'CONVERSATION_SESSION' AND source_session_id IS NOT NULL)",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("ck_care_event_source_type", "care_event", schema=SCHEMA)
    op.drop_column("care_event", "source_type", schema=SCHEMA)
