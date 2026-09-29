"""Bind assisted conversations to the revocable tablet session.

Revision ID: d8f0a2b4c657
Revises: c7e9f1a3b546
"""

import sqlalchemy as sa

from alembic import op

revision = "d8f0a2b4c657"
down_revision = "c7e9f1a3b546"
branch_labels = None
depends_on = None
SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.add_column(
        "conversation_session",
        sa.Column("assisted_session_id", sa.Uuid, nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_conversation_assisted_session",
        "conversation_session",
        "assisted_elder_session",
        ["assisted_session_id"],
        ["assisted_session_id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
    op.create_index(
        "ix_conversation_assisted_session",
        "conversation_session",
        ["assisted_session_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_assisted_session", table_name="conversation_session", schema=SCHEMA
    )
    op.drop_constraint("fk_conversation_assisted_session", "conversation_session", schema=SCHEMA)
    op.drop_column("conversation_session", "assisted_session_id", schema=SCHEMA)
