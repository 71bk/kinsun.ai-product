"""add speech synthesis replay and quota claims

Revision ID: f3a5b7c9d024
Revises: e2f4a6c8b013
Create Date: 2026-09-03 10:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f3a5b7c9d024"
down_revision: str | Sequence[str] | None = "e2f4a6c8b013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SECURITY_SCHEMA = "service_identity"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE {SECURITY_SCHEMA}.speech_synthesis_claim (
            capability_digest CHAR(64) PRIMARY KEY,
            tenant_id UUID NOT NULL,
            actor_id UUID NOT NULL,
            session_id UUID NOT NULL,
            agent_run_id UUID NOT NULL,
            client_ip_hash CHAR(64) NOT NULL,
            character_count INTEGER NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_speech_synthesis_digest
                CHECK (capability_digest ~ '^[a-f0-9]{{64}}$'),
            CONSTRAINT ck_speech_synthesis_client_hash
                CHECK (client_ip_hash ~ '^[a-f0-9]{{64}}$'),
            CONSTRAINT ck_speech_synthesis_character_count
                CHECK (character_count BETWEEN 1 AND 3000)
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_speech_synthesis_tenant_window "
        f"ON {SECURITY_SCHEMA}.speech_synthesis_claim (tenant_id, claimed_at)"
    )
    op.execute(
        f"CREATE INDEX ix_speech_synthesis_actor_window "
        f"ON {SECURITY_SCHEMA}.speech_synthesis_claim (actor_id, claimed_at)"
    )
    op.execute(
        f"CREATE INDEX ix_speech_synthesis_client_window "
        f"ON {SECURITY_SCHEMA}.speech_synthesis_claim (client_ip_hash, claimed_at)"
    )
    op.execute(
        f"COMMENT ON TABLE {SECURITY_SCHEMA}.speech_synthesis_claim IS "
        "'Single-use TTS capability claims and bounded per-client, actor, and tenant usage'"
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE {SECURITY_SCHEMA}.speech_synthesis_claim")
