"""Read-only schema/grant summary. Never print connection metadata or note content."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/core-api"))

from sqlalchemy import create_engine, text
from app.core.config import get_settings
from app.database_url import to_psycopg_database_url


def main():
    engine = create_engine(
        to_psycopg_database_url(get_settings().database_url),
        echo=False,
        hide_parameters=True,
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            revision = conn.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar_one()
            columns = list(
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='eldercare_ai' AND table_name='service_record' ORDER BY column_name"
                    )
                ).scalars()
            )
            rows = conn.execute(
                text("SELECT count(*) FROM eldercare_ai.service_record")
            ).scalar_one()
            grants = {
                p: conn.execute(
                    text(
                        "SELECT has_table_privilege(current_user, 'eldercare_ai.service_record', :privilege)"
                    ),
                    {"privilege": p},
                ).scalar_one()
                for p in ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
            }
            triggers = list(
                conn.execute(
                    text(
                        "SELECT tgname FROM pg_trigger WHERE tgrelid='eldercare_ai.service_record'::regclass "
                        "AND NOT tgisinternal ORDER BY tgname"
                    )
                ).scalars()
            )
            privileged = conn.execute(
                text(
                    "SELECT rolsuper OR rolbypassrls OR oid=(SELECT relowner FROM pg_class "
                    "WHERE oid='eldercare_ai.service_record'::regclass) FROM pg_roles WHERE rolname=current_user"
                )
            ).scalar_one()
            print(
                json.dumps(
                    {
                        "revision": revision,
                        "columns": columns,
                        "record_count": rows,
                        "configured_connection_privileged": privileged,
                        "configured_connection_grants": grants,
                        "triggers": triggers,
                    }
                )
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                {
                    "check": "failed",
                    "exception_type": type(error).__name__,
                    "sqlstate": getattr(getattr(error, "orig", None), "sqlstate", None),
                }
            )
        )
        sys.exit(1)
