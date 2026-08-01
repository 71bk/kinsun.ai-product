"""add terminal dead-letter outbox status

Revision ID: e4a1c8f29b73
Revises: d3b7e2a4f901
Create Date: 2026-08-01 11:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e4a1c8f29b73"
down_revision: str | Sequence[str] | None = "d3b7e2a4f901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "outbox_event_delivery_status_check",
        "outbox_event",
        schema="eldercare_ai",
        type_="check",
    )
    op.create_check_constraint(
        "outbox_event_delivery_status_check",
        "outbox_event",
        "delivery_status IN "
        "('PENDING','PUBLISHING','PUBLISHED','FAILED','SUPPRESSED','DEAD_LETTER')",
        schema="eldercare_ai",
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE eldercare_ai.outbox_event
        SET delivery_status = 'FAILED',
            last_error = COALESCE(last_error, 'DEAD_LETTER_STATUS_REMOVED')
        WHERE delivery_status = 'DEAD_LETTER'
        """
    )
    op.drop_constraint(
        "outbox_event_delivery_status_check",
        "outbox_event",
        schema="eldercare_ai",
        type_="check",
    )
    op.create_check_constraint(
        "outbox_event_delivery_status_check",
        "outbox_event",
        "delivery_status IN ('PENDING','PUBLISHING','PUBLISHED','FAILED','SUPPRESSED')",
        schema="eldercare_ai",
    )
