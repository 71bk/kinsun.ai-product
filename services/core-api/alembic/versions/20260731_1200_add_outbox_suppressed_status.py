"""add replay-safe suppressed outbox status

Revision ID: 8d9f27c4a6b1
Revises: f393b4452ce8
Create Date: 2026-07-31 12:00:00+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "8d9f27c4a6b1"
down_revision: Union[str, Sequence[str], None] = "f393b4452ce8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
        "delivery_status IN ('PENDING','PUBLISHING','PUBLISHED','FAILED','SUPPRESSED')",
        schema="eldercare_ai",
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE eldercare_ai.outbox_event
        SET delivery_status = 'FAILED',
            last_error = 'SUPPRESSED_STATUS_REMOVED'
        WHERE delivery_status = 'SUPPRESSED'
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
        "delivery_status IN ('PENDING','PUBLISHING','PUBLISHED','FAILED')",
        schema="eldercare_ai",
    )
