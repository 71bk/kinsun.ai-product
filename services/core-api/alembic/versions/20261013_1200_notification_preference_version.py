"""Add an optimistic revision to existing family notification preferences.

Revision ID: a1c3e5f7b902
Revises: f0b2c4d6e879
"""

from alembic import op

revision = "a1c3e5f7b902"
down_revision = "f0b2c4d6e879"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE eldercare_ai.notification_preference ADD COLUMN version integer NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE eldercare_ai.notification_preference ADD CONSTRAINT ck_notification_preference_version CHECK (version > 0)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE eldercare_ai.notification_preference DROP CONSTRAINT ck_notification_preference_version"
    )
    op.execute("ALTER TABLE eldercare_ai.notification_preference DROP COLUMN version")
