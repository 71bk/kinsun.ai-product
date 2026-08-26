import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "core-api"))

from app.core.config import get_settings
from app.database_url import to_psycopg_database_url


database_url = to_psycopg_database_url(get_settings().database_url)
engine = create_engine(database_url)
with engine.connect() as connection:
    row = connection.execute(
        text(
            """
            SELECT
              (SELECT count(*) FROM eldercare_ai.actor) AS actors,
              (SELECT count(*) FROM eldercare_ai.tenant) AS tenants,
              (SELECT count(*) FROM eldercare_ai.elder) AS elders,
              (SELECT count(*) FROM eldercare_ai.actor_tenant_membership) AS memberships,
              EXISTS(
                SELECT 1 FROM eldercare_ai.actor
                WHERE actor_id = '20000000-0000-4000-8000-000000000001'
              ) AS demo_elder
            """
        )
    ).mappings().one()

print(
    "actors={actors} tenants={tenants} elders={elders} "
    "memberships={memberships} demo_elder={demo_elder}".format(**row)
)
