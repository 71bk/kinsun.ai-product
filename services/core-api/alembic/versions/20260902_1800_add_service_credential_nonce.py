"""add shared service credential replay store

Revision ID: e2f4a6c8b013
Revises: d0e4f6a8b901
Create Date: 2026-09-02 18:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e2f4a6c8b013"
down_revision: str | Sequence[str] | None = "d0e4f6a8b901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NONCE_SCHEMA = "service_identity"


def upgrade() -> None:
    # Deliberately outside eldercare_ai. Replay claims are operational security
    # state, not domain state, and Agent Runtime must be able to claim its own
    # audience's nonces without ever holding a grant on a domain table.
    op.execute(f"CREATE SCHEMA {NONCE_SCHEMA}")
    op.execute(f"REVOKE ALL ON SCHEMA {NONCE_SCHEMA} FROM PUBLIC")

    op.execute(
        f"""
        CREATE TABLE {NONCE_SCHEMA}.credential_nonce (
            audience      VARCHAR(80)  NOT NULL,
            credential_id VARCHAR(128) NOT NULL,
            issuer        VARCHAR(80)  NOT NULL,
            subject       VARCHAR(80)  NOT NULL,
            expires_at    TIMESTAMPTZ  NOT NULL,
            claimed_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            PRIMARY KEY (audience, credential_id),
            CONSTRAINT ck_credential_nonce_identifiers
                CHECK (audience <> '' AND credential_id <> '')
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_credential_nonce_expiry "
        f"ON {NONCE_SCHEMA}.credential_nonce (expires_at)"
    )
    op.execute(
        f"COMMENT ON TABLE {NONCE_SCHEMA}.credential_nonce IS "
        "'Single-use service credential IDs claimed atomically across replicas; "
        "carries no restricted data and is purged after expiry'"
    )
    op.execute(
        f"COMMENT ON COLUMN {NONCE_SCHEMA}.credential_nonce.credential_id IS "
        "'The credential jti claim; unique per audience, never reusable'"
    )
    op.execute(
        f"COMMENT ON COLUMN {NONCE_SCHEMA}.credential_nonce.expires_at IS "
        "'Credential expiry; rows are purgeable once passed, never before'"
    )


def downgrade() -> None:
    op.execute(f"DROP SCHEMA {NONCE_SCHEMA} CASCADE")
