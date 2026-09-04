"""Read-only deployment check for the M-11 outbox delivery schema."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings

EXPECTED_REVISION = "b8d0f2a4c6e7"
EXPECTED_COLUMNS = {
    "next_attempt_at",
    "last_attempt_at",
    "lease_token",
    "lease_owner",
    "lease_expires_at",
    "last_dead_lettered_at",
    "last_dead_letter_reason",
    "redrive_count",
    "last_redriven_at",
}
EXPECTED_INDEXES = {
    "idx_outbox_delivery_due",
    "idx_outbox_expired_lease",
    "idx_outbox_dead_letter",
}
EXPECTED_CONSTRAINTS = {
    "ck_outbox_lease_state",
    "ck_outbox_published_at",
    "ck_outbox_dead_letter_metadata",
    "ck_outbox_redrive_count",
}


def main() -> None:
    settings = get_settings()
    database_url = settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    ).replace("ssl=", "sslmode=")
    engine = create_engine(database_url)
    try:
        try:
            with engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                columns = set(
                    connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'eldercare_ai' "
                            "AND table_name = 'outbox_event'"
                        )
                    ).scalars()
                )
                indexes = set(
                    connection.execute(
                        text(
                            "SELECT indexname FROM pg_indexes "
                            "WHERE schemaname = 'eldercare_ai' "
                            "AND tablename = 'outbox_event'"
                        )
                    ).scalars()
                )
                constraints = set(
                    connection.execute(
                        text(
                            "SELECT pg_constraint.conname FROM pg_constraint "
                            "JOIN pg_class ON pg_constraint.conrelid = pg_class.oid "
                            "JOIN pg_namespace ON pg_class.relnamespace = pg_namespace.oid "
                            "WHERE pg_namespace.nspname = 'eldercare_ai' "
                            "AND pg_class.relname = 'outbox_event'"
                        )
                    ).scalars()
                )
        except Exception as exc:
            print(f"outbox_schema connection_ok=False error_type={type(exc).__name__}")
            raise SystemExit(1) from None
    finally:
        engine.dispose()

    checks = {
        "revision": revision == EXPECTED_REVISION,
        "columns": EXPECTED_COLUMNS <= columns,
        "indexes": EXPECTED_INDEXES <= indexes,
        "constraints": EXPECTED_CONSTRAINTS <= constraints,
    }
    print("outbox_schema " + " ".join(f"{name}_ok={value}" for name, value in checks.items()))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
