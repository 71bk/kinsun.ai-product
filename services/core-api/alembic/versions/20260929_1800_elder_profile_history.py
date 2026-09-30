"""Versioned elder profiles, restricted history, and creator maintenance scopes.

Revision ID: e9a1b3c5d768
Revises: d8f0a2b4c657
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e9a1b3c5d768"
down_revision = "d8f0a2b4c657"
branch_labels = None
depends_on = None
SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.add_column(
        "elder",
        sa.Column("profile_version", sa.Integer, nullable=False, server_default="1"),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_elder_profile_version", "elder", "profile_version > 0", schema=SCHEMA
    )
    op.create_table(
        "elder_profile_change",
        sa.Column(
            "profile_change_id",
            sa.Uuid,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id", sa.Uuid, sa.ForeignKey(f"{SCHEMA}.tenant.tenant_id"), nullable=False
        ),
        sa.Column("elder_id", sa.Uuid, nullable=False),
        sa.Column(
            "care_profile_entry_id",
            sa.Uuid,
            sa.ForeignKey(
                f"{SCHEMA}.elder_care_profile_entry.care_profile_entry_id", ondelete="RESTRICT"
            ),
        ),
        sa.Column(
            "changed_by_actor_id",
            sa.Uuid,
            sa.ForeignKey(f"{SCHEMA}.actor.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("change_type", sa.String(32), nullable=False),
        sa.Column("resource_version", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("before_data", postgresql.JSONB, nullable=True),
        sa.Column("after_data", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["elder_id", "tenant_id"],
            [f"{SCHEMA}.elder.elder_id", f"{SCHEMA}.elder.tenant_id"],
            name="fk_profile_change_elder_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "change_type IN ('BASIC_UPDATED','CARE_ENTRY_CREATED',"
            "'CARE_ENTRY_UPDATED','CARE_ENTRY_RETIRED')",
            name="ck_profile_change_type",
        ),
        sa.CheckConstraint("resource_version > 0", name="ck_profile_change_version"),
        sa.CheckConstraint(
            "length(btrim(reason)) BETWEEN 1 AND 200", name="ck_profile_change_reason"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_profile_change_history",
        "elder_profile_change",
        ["tenant_id", "elder_id", "created_at", "profile_change_id"],
        schema=SCHEMA,
    )
    # Only untouched default creator grants. JSONB containment in both directions
    # permits ordering differences but cannot restore a removed/restricted scope.
    op.execute(
        sa.text("""
        UPDATE eldercare_ai.care_relationship r
        SET scope = r.scope || '["elder:profile:update","care_profile:write"]'::jsonb,
            updated_at = now()
        FROM eldercare_ai.elder e, eldercare_ai.elder_enrollment n,
             eldercare_ai.actor a, eldercare_ai.care_unit u
        WHERE r.elder_id = e.elder_id AND r.tenant_id = e.tenant_id
          AND e.actor_id IS NULL AND e.status = 'ACTIVE'
          AND n.elder_id = e.elder_id AND n.tenant_id = r.tenant_id
          AND n.created_by_actor_id = r.actor_id AND n.care_unit_id = r.care_unit_id
          AND n.enrollment_type = 'ORGANIZATION' AND n.status = 'ACTIVE'
          AND n.valid_from <= now() AND (n.valid_until IS NULL OR n.valid_until > now())
          AND a.actor_id = r.actor_id AND a.actor_type = 'DAYCARE_CARE_WORKER'
          AND a.status = 'ACTIVE'
          AND u.care_unit_id = r.care_unit_id AND u.tenant_id = r.tenant_id AND u.status = 'ACTIVE'
          AND r.relationship_type = 'DAYCARE_ASSIGNMENT' AND r.status = 'ACTIVE'
          AND r.effective_from <= now() AND (r.effective_to IS NULL OR r.effective_to > now())
          AND r.scope @> '["elder:basic:read","elder:access_context:read","care_profile:read",
            "assisted_session:create","voice_session:create","voice_session:read",
            "voice_session:control","consent:read"]'::jsonb
          AND r.scope <@ '["elder:basic:read","elder:access_context:read","care_profile:read",
            "assisted_session:create","voice_session:create","voice_session:read",
            "voice_session:control","consent:read"]'::jsonb
          AND EXISTS (SELECT 1 FROM eldercare_ai.tenant t
            WHERE t.tenant_id = r.tenant_id AND t.status = 'ACTIVE')
          AND EXISTS (SELECT 1 FROM eldercare_ai.actor_tenant_membership m
            WHERE m.actor_id = r.actor_id AND m.tenant_id = r.tenant_id
              AND m.care_unit_id IS NULL AND m.status = 'ACTIVE'
              AND m.effective_from <= now() AND (m.effective_to IS NULL OR m.effective_to > now()))
          AND EXISTS (SELECT 1 FROM eldercare_ai.actor_tenant_membership m
            WHERE m.actor_id = r.actor_id AND m.tenant_id = r.tenant_id
              AND m.care_unit_id = r.care_unit_id AND m.status = 'ACTIVE'
              AND m.effective_from <= now() AND (m.effective_to IS NULL OR m.effective_to > now()))
    """)
    )


def downgrade() -> None:
    # Remove only this feature's scopes when removing the feature itself.
    op.execute(
        sa.text("""
        UPDATE eldercare_ai.care_relationship
        SET scope = scope - 'elder:profile:update' - 'care_profile:write'
        WHERE jsonb_typeof(scope) = 'array'
          AND scope ?| array['elder:profile:update','care_profile:write']
    """)
    )
    op.drop_table("elder_profile_change", schema=SCHEMA)
    op.drop_constraint("ck_elder_profile_version", "elder", schema=SCHEMA)
    op.drop_column("elder", "profile_version", schema=SCHEMA)
