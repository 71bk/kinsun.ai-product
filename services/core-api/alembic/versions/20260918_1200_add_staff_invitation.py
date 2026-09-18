"""Add hash-only development workforce invitations.

Revision ID: c7e9f1a3b546
Revises: b6d8f0a2c435
"""

import sqlalchemy as sa

from alembic import op

revision = "c7e9f1a3b546"
down_revision = "b6d8f0a2c435"
branch_labels = None
depends_on = None
SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.create_table(
        "staff_invitation",
        sa.Column(
            "staff_invitation_id",
            sa.Uuid,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id", sa.Uuid, sa.ForeignKey(f"{SCHEMA}.tenant.tenant_id"), nullable=False
        ),
        sa.Column(
            "issued_by_actor_id", sa.Uuid, sa.ForeignKey(f"{SCHEMA}.actor.actor_id"), nullable=False
        ),
        sa.Column(
            "care_unit_id",
            sa.Uuid,
            sa.ForeignKey(f"{SCHEMA}.care_unit.care_unit_id"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role_code", sa.String(64), nullable=False),
        sa.Column("email_digest", sa.String(64), nullable=False),
        sa.Column("digest_key_version", sa.Integer, nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ISSUED"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by_actor_id", sa.Uuid, sa.ForeignKey(f"{SCHEMA}.actor.actor_id")),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "role_code IN ('DAYCARE_CARE_WORKER','HOME_CARE_WORKER')",
            name="ck_staff_invitation_role",
        ),
        sa.CheckConstraint(
            "status IN ('ISSUED','ACCEPTED','REVOKED')", name="ck_staff_invitation_status"
        ),
        sa.CheckConstraint(
            "version > 0 AND digest_key_version > 0", name="ck_staff_invitation_version"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_staff_invitation_expiry"),
        sa.CheckConstraint(
            "(status = 'ACCEPTED' AND accepted_at IS NOT NULL AND accepted_by_actor_id IS NOT NULL)"
            " OR (status <> 'ACCEPTED' AND accepted_at IS NULL AND accepted_by_actor_id IS NULL)",
            name="ck_staff_invitation_acceptance",
        ),
        sa.CheckConstraint(
            "(status = 'REVOKED') = (revoked_at IS NOT NULL)", name="ck_staff_invitation_revocation"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_staff_invitation_tenant_created",
        "staff_invitation",
        ["tenant_id", "created_at", "staff_invitation_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("staff_invitation", schema=SCHEMA)
