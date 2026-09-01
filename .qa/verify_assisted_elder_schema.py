"""Read-only verification for the staff-assisted Elder schema revision."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-api"))

from app.core.config import get_settings  # noqa: E402
from app.database_url import to_psycopg_database_url  # noqa: E402

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
    "ck_consent_confirmation_provenance",
    "fk_consent_assisted_session",
    "fk_consent_recorded_by_actor",
}
EXPECTED_CONSENT_COLUMNS = {
    "confirmation_method",
    "recorded_by_actor_id",
    "assisted_session_id",
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
            consent_columns = set(
                connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'eldercare_ai' "
                        "AND table_name = 'consent_grant' "
                        "AND column_name = ANY(:names)"
                    ),
                    {"names": sorted(EXPECTED_CONSENT_COLUMNS)},
                ).scalars()
            )
    finally:
        engine.dispose()

    assert revision == "b8c2d4e5f607", revision
    assert tables == EXPECTED_TABLES, sorted(tables)
    assert constraints == EXPECTED_CONSTRAINTS, sorted(constraints)
    assert consent_columns == EXPECTED_CONSENT_COLUMNS, sorted(consent_columns)
    print(f"revision={revision}")
    print(f"verified_tables={len(tables)}")
    print(f"verified_constraints={len(constraints)}")
    print(f"verified_consent_columns={len(consent_columns)}")


if __name__ == "__main__":
    main()
