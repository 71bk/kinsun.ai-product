"""Version the baseline service_record table without promoting legacy rows.

Revision ID: e3a5c7d9f102
Revises: d1f3a5c7e9b0
"""

import sqlalchemy as sa

from alembic import op

revision = "e3a5c7d9f102"
down_revision = "d1f3a5c7e9b0"
branch_labels = None
depends_on = None
SCHEMA = "eldercare_ai"


def upgrade() -> None:
    op.add_column("service_record", sa.Column("tenant_id", sa.UUID(), nullable=True), schema=SCHEMA)
    op.create_foreign_key(
        "fk_service_record_tenant",
        "service_record",
        "tenant",
        ["tenant_id"],
        ["tenant_id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
    op.add_column(
        "service_record", sa.Column("service_timezone", sa.String(64), nullable=True), schema=SCHEMA
    )
    op.add_column(
        "service_record",
        sa.Column("assignment_version", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "service_record", sa.Column("version", sa.Integer(), nullable=True), schema=SCHEMA
    )
    op.create_check_constraint(
        "ck_service_record_v1",
        "service_record",
        "version IS NULL OR (version = 1 AND tenant_id IS NOT NULL AND "
        "service_timezone IS NOT NULL AND assignment_version IS NOT NULL AND assignment_version >= 1 "
        "AND status = 'COMPLETED' AND completed_at IS NOT NULL AND record_type = 'SERVICE_NOTE' "
        "AND jsonb_typeof(content) = 'object' AND content ? 'note' "
        "AND jsonb_typeof(content->'note') = 'string' "
        "AND length(btrim(content->>'note')) BETWEEN 1 AND 4000)",
        schema=SCHEMA,
    )
    op.create_index(
        "uq_service_record_single_note",
        "service_record",
        ["assignment_id", "record_type"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("version = 1"),
    )
    op.execute(f"""
        CREATE FUNCTION {SCHEMA}.prevent_service_record_v1_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.version IS NOT NULL OR (TG_OP = 'UPDATE' AND NEW.version IS NOT NULL) THEN
            RAISE EXCEPTION 'formal service record is immutable';
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_service_record_immutable BEFORE UPDATE OR DELETE
        ON {SCHEMA}.service_record FOR EACH ROW
        EXECUTE FUNCTION {SCHEMA}.prevent_service_record_v1_mutation();
    """)


def downgrade() -> None:
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {SCHEMA}.service_record "
        "WHERE version IS NOT NULL) THEN RAISE EXCEPTION "
        "'cannot remove formal service record schema while data exists'; END IF; END $$;"
    )
    op.execute(f"DROP TRIGGER trg_service_record_immutable ON {SCHEMA}.service_record")
    op.execute(f"DROP FUNCTION {SCHEMA}.prevent_service_record_v1_mutation()")
    op.drop_index("uq_service_record_single_note", table_name="service_record", schema=SCHEMA)
    op.drop_constraint("ck_service_record_v1", "service_record", schema=SCHEMA, type_="check")
    op.drop_constraint(
        "fk_service_record_tenant", "service_record", schema=SCHEMA, type_="foreignkey"
    )
    for column in ["version", "assignment_version", "service_timezone", "tenant_id"]:
        op.drop_column("service_record", column, schema=SCHEMA)
