"""Read-only, aggregate-only scope for the pending development key rotation."""

import asyncio
import json
import sys
from pathlib import Path
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "services/core-api"))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import Settings


async def main():
    settings = Settings(_env_file=root / ".env")
    if settings.app_env != "development":
        raise RuntimeError("Development only")
    root_values = dotenv_values(root / ".env")
    bff_values = dotenv_values(root / "packages/frontend/.env.local")
    keys = [
        "KINSUN_IDENTITY_HMAC_SECRET",
        "KINSUN_EMAIL_CHALLENGE_HMAC_SECRET",
        "KINSUN_AUTH_HANDOFF_SECRET",
        "KINSUN_SYNTHETIC_EMAIL_CODE_SECRET",
    ]
    engine = create_async_engine(
        settings.database_url, echo=False, hide_parameters=True
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            result = (
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) AS active_kinsun_identities, count(*) FILTER (WHERE a.email IS NOT NULL AND length(trim(a.email)) > 0) AS actor_email_present, count(DISTINCT i.digest_key_version) AS active_key_versions FROM eldercare_ai.external_identity i JOIN eldercare_ai.actor a ON a.actor_id=i.actor_id WHERE i.provider='KINSUN' AND i.status='ACTIVE'"
                        )
                    )
                )
                .mappings()
                .one()
            )
            report = dict(result)
            report["bff_local_settings"] = [
                {
                    "name": key,
                    "present": bool(bff_values.get(key)),
                    "matches_root": bff_values.get(key) == root_values.get(key),
                }
                for key in keys
            ]
            (root / ".qa/auth-rotation-impact.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(json.dumps(report))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
