"""Read-only verification for the staff-assisted Elder schema revision."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.database_url import to_psycopg_database_url

EXPECTED_TABLES = {
    "assisted_elder_session",
    "elder_care_profile_entry",
    "elder_enrollment",
}
EXPECTED_CONSTRAINTS = {
    "ck_assisted_elder_session_pairing_digest",
    "ck_assisted_elder_session_token_digest",
    "fk_assisted_elder_session_enrollment_scope",
    "fk_elder_care_profile_elder_tenant",
    "fk_elder_enrollment_elder_tenant",
    "uq_elder_scope",
}


def main() -> None:
    database_url = to_psycopg_database_url(get_settings().database_url)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()
            tables = set(
                connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'eldercare_ai' "
                        "AND table_name = ANY(:names)"
                    ),
                    {"names": sorted(EXPECTED_TABLES)},
                ).scalars()
            )
            constraints = set(
                connection.execute(
                    text(
                        "SELECT constraint_name "
                        "FROM information_schema.table_constraints "
                        "WHERE constraint_schema = 'eldercare_ai' "
                        "AND constraint_name = ANY(:names)"
                    ),
                    {"names": sorted(EXPECTED_CONSTRAINTS)},
                ).scalars()
            )
    finally:
        engine.dispose()

    assert revision == "f7a9b1c3d456", revision
    assert tables == EXPECTED_TABLES, sorted(tables)
    assert constraints == EXPECTED_CONSTRAINTS, sorted(constraints)
    print(f"revision={revision}")
    print(f"verified_tables={len(tables)}")
    print(f"verified_constraints={len(constraints)}")


if __name__ == "__main__":
    main()
