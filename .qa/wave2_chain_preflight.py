"""Read-only synthetic account and configuration inventory; no credentials in output."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/core-api"))
from app.core.config import get_settings
from app.database_url import to_psycopg_database_url
from sqlalchemy import create_engine, text


def main():
    s = get_settings()
    print(
        json.dumps(
            {
                k: getattr(s, k)
                for k in (
                    "app_env",
                    "fake_auth_enabled",
                    "kinsun_native_auth_enabled",
                    "app_session_auth_enabled",
                    "agent_runtime_model_id",
                )
            }
        )
    )
    engine = create_engine(
        to_psycopg_database_url(s.database_url),
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
    )
    with engine.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        queries = {
            "actors": "SELECT actor_id, actor_type, status, EXISTS(SELECT 1 FROM eldercare_ai.password_credential p WHERE p.actor_id=a.actor_id) AS credential FROM eldercare_ai.actor a WHERE actor_id IN ('20000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000010')",
            "elders": "SELECT elder_id, tenant_id, primary_care_unit_id, status FROM eldercare_ai.elder WHERE actor_id='20000000-0000-4000-8000-000000000001'",
            "consents": "SELECT purpose_code,status,version, effective_at<=now() AND (expires_at IS NULL OR expires_at>now()) AS current FROM eldercare_ai.consent_grant WHERE elder_id IN (SELECT elder_id FROM eldercare_ai.elder WHERE actor_id='20000000-0000-4000-8000-000000000001')",
            "relationships": "SELECT relationship_id,actor_id,relationship_type,scope,status,effective_from<=now() AND (effective_to IS NULL OR effective_to>now()) AS current FROM eldercare_ai.care_relationship WHERE elder_id IN (SELECT elder_id FROM eldercare_ai.elder WHERE actor_id='20000000-0000-4000-8000-000000000001') AND actor_id IN ('20000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000010')",
            "memberships": "SELECT actor_id,tenant_id,care_unit_id,role_code,status,effective_from<=now() AND (effective_to IS NULL OR effective_to>now()) AS current FROM eldercare_ai.actor_tenant_membership WHERE actor_id IN ('20000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000010')",
        }
        for name, q in queries.items():
            print(
                name
                + "="
                + json.dumps(
                    [dict(r) for r in c.execute(text(q)).mappings()], default=str
                )
            )
    engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error_type": type(e).__name__}))
        raise SystemExit(1) from None
