"""Read-only, bounded synthetic staff/environment preflight; never prints credentials."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/core-api"))
from dotenv import load_dotenv

from app.core.config import get_settings
from app.database_url import to_psycopg_database_url
from sqlalchemy import create_engine, text
import os


def main():
    load_dotenv(ROOT / ".env")
    settings = get_settings()
    print(
        json.dumps(
            {
                "app_env": str(settings.app_env),
                "native_auth": settings.kinsun_native_auth_enabled,
                "app_session_auth": settings.app_session_auth_enabled,
                "fake_auth": settings.fake_auth_enabled,
                "demo_password_present": bool(os.getenv("DEMO_ACCOUNT_PASSWORD")),
                "frontend_auth_secret_present": bool(
                    os.getenv("KINSUN_AUTH_HANDOFF_SECRET")
                ),
            }
        )
    )
    engine = create_engine(
        to_psycopg_database_url(settings.database_url),
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
    )
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        print(
            "revision="
            + str(conn.scalar(text("SELECT version_num FROM public.alembic_version")))
        )
        rows = (
            conn.execute(
                text("""
            SELECT a.actor_type, a.status, m.tenant_id, m.care_unit_id, m.role_code,
                   m.status AS membership_status,
                   m.effective_from <= now() AND (m.effective_to IS NULL OR m.effective_to > now()) AS current,
                   EXISTS (SELECT 1 FROM eldercare_ai.password_credential p WHERE p.actor_id=a.actor_id) AS credential_present
            FROM eldercare_ai.actor a
            LEFT JOIN eldercare_ai.actor_tenant_membership m ON m.actor_id=a.actor_id
            WHERE a.actor_id='20000000-0000-4000-8000-000000000010'
        """)
            )
            .mappings()
            .all()
        )
        print("synthetic_staff=" + json.dumps([dict(row) for row in rows], default=str))
    engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__}))
        raise SystemExit(1) from None
