"""add staff-assisted accountless Elder session foundation

Revision ID: f7a9b1c3d456
Revises: e6f8a0b2c345
Create Date: 2026-09-01 10:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f7a9b1c3d456"
down_revision: str | Sequence[str] | None = "e6f8a0b2c345"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_elder_scope",
        "elder",
        ["elder_id", "tenant_id"],
        schema=SCHEMA,
    )
    op.create_table(
        "elder_enrollment",
        sa.Column(
            "enrollment_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("elder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("care_unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "enrollment_type",
            sa.String(length=32),
            server_default=sa.text("'ORGANIZATION'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_reason", sa.String(length=120), nullable=True),
        sa.Column("created_by_actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "enrollment_type IN ('ORGANIZATION')", name="ck_elder_enrollment_type"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','ACTIVE','SUSPENDED','ENDED')",
            name="ck_elder_enrollment_status",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_elder_enrollment_window",
        ),
        sa.CheckConstraint(
            "(status = 'ENDED' AND ended_at IS NOT NULL AND ended_reason IS NOT NULL) "
            "OR (status <> 'ENDED' AND ended_at IS NULL)",
            name="ck_elder_enrollment_end_state",
        ),
        sa.ForeignKeyConstraint(
            ["elder_id", "tenant_id"],
            [f"{SCHEMA}.elder.elder_id", f"{SCHEMA}.elder.tenant_id"],
            name="fk_elder_enrollment_elder_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["care_unit_id"],
            [f"{SCHEMA}.care_unit.care_unit_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_actor_id"],
            [f"{SCHEMA}.actor.actor_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("enrollment_id"),
        sa.UniqueConstraint(
            "enrollment_id",
            "elder_id",
            "tenant_id",
            name="uq_elder_enrollment_scope",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_elder_enrollment_active_lookup",
        "elder_enrollment",
        ["tenant_id", "elder_id", "status", "valid_from", "valid_until"],
        schema=SCHEMA,
    )

    op.create_table(
        "elder_care_profile_entry",
        sa.Column(
            "care_profile_entry_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("elder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "source_type",
            sa.String(length=48),
            server_default=sa.text("'STAFF_RECORDED'"),
            nullable=False,
        ),
        sa.Column("source_actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(length=24),
            server_default=sa.text("'RECORDED'"),
            nullable=False,
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('HEALTH_CONDITION','MEDICATION','ALLERGY','CARE_PRECAUTION')",
            name="ck_elder_care_profile_category",
        ),
        sa.CheckConstraint(
            "source_type IN ('STAFF_RECORDED','ELDER_REPORTED',"
            "'LEGAL_REPRESENTATIVE_REPORTED','CLINICAL_DOCUMENT')",
            name="ck_elder_care_profile_source_type",
        ),
        sa.CheckConstraint(
            "verification_status IN ('RECORDED','VERIFIED','DISPUTED','RETIRED')",
            name="ck_elder_care_profile_verification",
        ),
        sa.CheckConstraint(
            "length(btrim(content)) BETWEEN 1 AND 500",
            name="ck_elder_care_profile_content",
        ),
        sa.CheckConstraint(
            "(verification_status = 'RETIRED' AND retired_at IS NOT NULL) "
            "OR (verification_status <> 'RETIRED' AND retired_at IS NULL)",
            name="ck_elder_care_profile_retired_state",
        ),
        sa.CheckConstraint("version > 0", name="ck_elder_care_profile_version"),
        sa.ForeignKeyConstraint(
            ["elder_id", "tenant_id"],
            [f"{SCHEMA}.elder.elder_id", f"{SCHEMA}.elder.tenant_id"],
            name="fk_elder_care_profile_elder_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_actor_id"],
            [f"{SCHEMA}.actor.actor_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("care_profile_entry_id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_elder_care_profile_context",
        "elder_care_profile_entry",
        ["tenant_id", "elder_id", "verification_status", "created_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "assisted_elder_session",
        sa.Column(
            "assisted_session_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("elder_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("initiated_by_actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "initiator_mode",
            sa.String(length=24),
            server_default=sa.text("'STAFF_ASSISTED'"),
            nullable=False,
        ),
        sa.Column("authorization_source_type", sa.String(length=24), nullable=False),
        sa.Column("authorization_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pairing_token_digest", sa.CHAR(length=64), nullable=False),
        sa.Column("session_token_digest", sa.CHAR(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'PAIRING'"),
            nullable=False,
        ),
        sa.Column("pairing_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pairing_token_digest ~ '^[0-9a-f]{64}$'",
            name="ck_assisted_elder_session_pairing_digest",
        ),
        sa.CheckConstraint(
            "session_token_digest IS NULL OR session_token_digest ~ '^[0-9a-f]{64}$'",
            name="ck_assisted_elder_session_token_digest",
        ),
        sa.CheckConstraint(
            "status IN ('PAIRING','ACTIVE','ENDED','EXPIRED')",
            name="ck_assisted_elder_session_status",
        ),
        sa.CheckConstraint(
            "initiator_mode = 'STAFF_ASSISTED'", name="ck_assisted_elder_session_mode"
        ),
        sa.CheckConstraint(
            "authorization_source_type IN ('RELATIONSHIP','ASSIGNMENT')",
            name="ck_assisted_elder_session_authorization_source",
        ),
        sa.CheckConstraint(
            "pairing_expires_at > created_at AND absolute_expires_at > created_at",
            name="ck_assisted_elder_session_expiry",
        ),
        sa.CheckConstraint(
            "idle_expires_at IS NULL OR idle_expires_at <= absolute_expires_at",
            name="ck_assisted_elder_session_idle_expiry",
        ),
        sa.CheckConstraint(
            "(status = 'PAIRING' AND session_token_digest IS NULL "
            "AND activated_at IS NULL AND last_seen_at IS NULL "
            "AND idle_expires_at IS NULL AND ended_at IS NULL) OR "
            "(status = 'ACTIVE' AND session_token_digest IS NOT NULL "
            "AND activated_at IS NOT NULL AND last_seen_at IS NOT NULL "
            "AND idle_expires_at IS NOT NULL AND ended_at IS NULL) OR "
            "(status IN ('ENDED','EXPIRED') AND ended_at IS NOT NULL)",
            name="ck_assisted_elder_session_state_shape",
        ),
        sa.CheckConstraint("version > 0", name="ck_assisted_elder_session_version"),
        sa.ForeignKeyConstraint(
            ["elder_id", "tenant_id"],
            [f"{SCHEMA}.elder.elder_id", f"{SCHEMA}.elder.tenant_id"],
            name="fk_assisted_elder_session_elder_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id", "elder_id", "tenant_id"],
            [
                f"{SCHEMA}.elder_enrollment.enrollment_id",
                f"{SCHEMA}.elder_enrollment.elder_id",
                f"{SCHEMA}.elder_enrollment.tenant_id",
            ],
            name="fk_assisted_elder_session_enrollment_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_actor_id"],
            [f"{SCHEMA}.actor.actor_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("assisted_session_id"),
        sa.UniqueConstraint(
            "pairing_token_digest", name="uq_assisted_elder_session_pairing_digest"
        ),
        sa.UniqueConstraint(
            "session_token_digest", name="uq_assisted_elder_session_token_digest"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_assisted_elder_session_active",
        "assisted_elder_session",
        ["tenant_id", "elder_id", "status", "absolute_expires_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_assisted_elder_session_initiator",
        "assisted_elder_session",
        ["initiated_by_actor_id", "status", "absolute_expires_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assisted_elder_session_initiator",
        table_name="assisted_elder_session",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_assisted_elder_session_active",
        table_name="assisted_elder_session",
        schema=SCHEMA,
    )
    op.drop_table("assisted_elder_session", schema=SCHEMA)
    op.drop_index(
        "ix_elder_care_profile_context",
        table_name="elder_care_profile_entry",
        schema=SCHEMA,
    )
    op.drop_table("elder_care_profile_entry", schema=SCHEMA)
    op.drop_index(
        "ix_elder_enrollment_active_lookup",
        table_name="elder_enrollment",
        schema=SCHEMA,
    )
    op.drop_table("elder_enrollment", schema=SCHEMA)
    op.drop_constraint("uq_elder_scope", "elder", schema=SCHEMA, type_="unique")
