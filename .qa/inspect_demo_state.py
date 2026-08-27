import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "core-api"))

from app.core.config import get_settings
from app.database_url import to_psycopg_database_url


database_url = to_psycopg_database_url(get_settings().database_url)
engine = create_engine(database_url, hide_parameters=True)
with engine.connect() as connection:
    row = (
        connection.execute(
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
        )
        .mappings()
        .one()
    )
    policy = (
        connection.execute(
            text(
                """
            SELECT
              policy_type,
              status,
              policy_payload ->> 'synthetic_only' AS synthetic_only,
              policy_payload ->> 'purpose_specific' AS purpose_specific,
              policy_payload ->> 'production_approved' AS production_approved,
              policy_payload ->> 'governance_status' AS governance_status,
              owner_tenant_id IS NULL AS is_global
            FROM eldercare_ai.policy_registry
            WHERE policy_code = 'demo-consent-policy'
              AND version = 'demo-consent-v1'
            """
            )
        )
        .mappings()
        .one_or_none()
    )

print(
    "actors={actors} tenants={tenants} elders={elders} "
    "memberships={memberships} demo_elder={demo_elder}".format(**row)
)
print("demo_policy=" + json.dumps(dict(policy) if policy else None, default=str))
