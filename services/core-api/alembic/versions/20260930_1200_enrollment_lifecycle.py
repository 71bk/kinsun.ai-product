"""Versioned enrollment lifecycle and restricted immutable transition history.

Revision ID: f0b2c4d6e879
Revises: e9a1b3c5d768
"""

import sqlalchemy as sa

from alembic import op

revision = "f0b2c4d6e879"
down_revision = "e9a1b3c5d768"
branch_labels = None
depends_on = None
SCHEMA = "eldercare_ai"

# Deliberately excludes reduced/custom grants and requires the original creator.
BACKFILL_SQL = """
UPDATE eldercare_ai.care_relationship r
SET scope = r.scope || '["enrollment:read","enrollment:manage"]'::jsonb, updated_at = now()
FROM eldercare_ai.elder e, eldercare_ai.elder_enrollment n,
     eldercare_ai.actor a, eldercare_ai.care_unit u
WHERE r.elder_id = e.elder_id AND r.tenant_id = e.tenant_id
  AND e.actor_id IS NULL AND e.status = 'ACTIVE'
  AND n.elder_id = e.elder_id AND n.tenant_id = r.tenant_id
  AND n.created_by_actor_id = r.actor_id AND n.care_unit_id = r.care_unit_id
  AND n.enrollment_type = 'ORGANIZATION' AND n.status = 'ACTIVE'
  AND n.valid_from <= now() AND (n.valid_until IS NULL OR n.valid_until > now())
  AND a.actor_id = r.actor_id AND a.actor_type = 'DAYCARE_CARE_WORKER' AND a.status = 'ACTIVE'
  AND u.care_unit_id = r.care_unit_id AND u.tenant_id = r.tenant_id AND u.status = 'ACTIVE'
  AND r.relationship_type = 'DAYCARE_ASSIGNMENT' AND r.status = 'ACTIVE'
  AND r.effective_from <= now() AND (r.effective_to IS NULL OR r.effective_to > now())
  AND r.scope @> '["elder:profile:update","care_profile:write","elder:basic:read",
    "elder:access_context:read","care_profile:read","assisted_session:create",
    "voice_session:create","voice_session:read","voice_session:control","consent:read"]'::jsonb
  AND r.scope <@ '["elder:profile:update","care_profile:write","elder:basic:read",
    "elder:access_context:read","care_profile:read","assisted_session:create",
    "voice_session:create","voice_session:read","voice_session:control","consent:read"]'::jsonb
  AND EXISTS (SELECT 1 FROM eldercare_ai.tenant t
    WHERE t.tenant_id = r.tenant_id AND t.status = 'ACTIVE')
  AND EXISTS (SELECT 1 FROM eldercare_ai.actor_tenant_membership m
    WHERE m.actor_id = r.actor_id AND m.tenant_id = r.tenant_id
      AND m.role_code = 'DAYCARE_CARE_WORKER' AND m.care_unit_id IS NULL AND m.status = 'ACTIVE'
      AND m.effective_from <= now() AND (m.effective_to IS NULL OR m.effective_to > now()))
  AND EXISTS (SELECT 1 FROM eldercare_ai.actor_tenant_membership m
    WHERE m.actor_id = r.actor_id AND m.tenant_id = r.tenant_id
      AND m.role_code = 'DAYCARE_CARE_WORKER'
      AND m.care_unit_id = r.care_unit_id AND m.status = 'ACTIVE'
      AND m.effective_from <= now() AND (m.effective_to IS NULL OR m.effective_to > now()))
"""


def upgrade():
    op.add_column(
        "elder_enrollment",
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_elder_enrollment_version", "elder_enrollment", "version > 0", schema=SCHEMA
    )
    op.create_table(
        "elder_enrollment_change",
        sa.Column(
            "enrollment_change_id",
            sa.Uuid,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("enrollment_id", sa.Uuid, nullable=False),
        sa.Column("elder_id", sa.Uuid, nullable=False),
        sa.Column(
            "tenant_id", sa.Uuid, sa.ForeignKey(f"{SCHEMA}.tenant.tenant_id"), nullable=False
        ),
        sa.Column(
            "changed_by_actor_id",
            sa.Uuid,
            sa.ForeignKey(f"{SCHEMA}.actor.actor_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(20), nullable=False),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id", "elder_id", "tenant_id"],
            [f"{SCHEMA}.elder_enrollment.{c}" for c in ("enrollment_id", "elder_id", "tenant_id")],
            name="fk_enrollment_change_scope",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "from_status IN ('ACTIVE','SUSPENDED')", name="ck_enrollment_change_from"
        ),
        sa.CheckConstraint(
            "to_status IN ('ACTIVE','SUSPENDED','ENDED')", name="ck_enrollment_change_to"
        ),
        sa.CheckConstraint("from_status <> to_status", name="ck_enrollment_change_transition"),
        sa.CheckConstraint("version > 1", name="ck_enrollment_change_version"),
        sa.CheckConstraint(
            "length(btrim(reason)) BETWEEN 1 AND 120", name="ck_enrollment_change_reason"
        ),
        sa.UniqueConstraint("enrollment_id", "version", name="uq_enrollment_change_version"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_enrollment_change_history",
        "elder_enrollment_change",
        ["tenant_id", "enrollment_id", "created_at", "enrollment_change_id"],
        schema=SCHEMA,
    )
    op.execute(
        sa.text("""
        CREATE FUNCTION eldercare_ai.reject_enrollment_history_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Enrollment history is immutable' USING ERRCODE = '23514';
        END $$
    """)
    )
    op.execute(
        sa.text("""
        CREATE TRIGGER enrollment_history_immutable BEFORE UPDATE OR DELETE
        ON eldercare_ai.elder_enrollment_change FOR EACH ROW
        EXECUTE FUNCTION eldercare_ai.reject_enrollment_history_mutation()
    """)
    )
    op.execute(sa.text(BACKFILL_SQL))


def downgrade():
    op.execute(
        sa.text("""
        UPDATE eldercare_ai.care_relationship
        SET scope = scope - 'enrollment:read' - 'enrollment:manage'
        WHERE jsonb_typeof(scope) = 'array'
          AND scope ?| array['enrollment:read','enrollment:manage']
    """)
    )
    op.drop_table("elder_enrollment_change", schema=SCHEMA)
    op.execute(sa.text("DROP FUNCTION eldercare_ai.reject_enrollment_history_mutation()"))
    op.drop_constraint("ck_elder_enrollment_version", "elder_enrollment", schema=SCHEMA)
    op.drop_column("elder_enrollment", "version", schema=SCHEMA)
