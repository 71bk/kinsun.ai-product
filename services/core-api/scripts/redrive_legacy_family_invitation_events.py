"""One-time local QA redrive for legacy invitation event-name aliases."""

import psycopg

from app.core.config import get_settings

database_url = get_settings().database_url.replace(
    "postgresql+asyncpg://", "postgresql://"
).replace("ssl=", "sslmode=")
with psycopg.connect(database_url) as connection:
    cursor = connection.execute(
        """
        UPDATE eldercare_ai.outbox_event
        SET delivery_status = 'FAILED', attempt_count = 0, last_error = NULL
        WHERE delivery_status = 'DEAD_LETTER'
          AND last_error = 'PUBLISHER_UNEXPECTED_ERROR'
          AND event_type IN (
            'family_invitation.issued.v1',
            'family_invitation.redeemed.v1',
            'family_invitation.revoked.v1'
          )
        """
    )
    print(f"redriven={cursor.rowcount}")
