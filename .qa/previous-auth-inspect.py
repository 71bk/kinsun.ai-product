"""Synthetic login probe plus read-only credential checks; emits safe metadata only."""

import asyncio
import importlib.util
import json
import httpx
from dotenv import dotenv_values
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "previous_auth_fixture", root / "scripts/qa/previous_record_fixture.py"
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


async def main():
    settings = fixture.Settings(_env_file=root / ".env")
    fixture.validate_target(settings.app_env, settings.database_url)
    private = json.loads(fixture.PRIVATE.read_text())
    if private.get("retired") or "accounts" not in private:
        raise RuntimeError("An active synthetic campaign is required")
    values = dotenv_values(root / ".env")
    print(
        json.dumps(
            {
                "handoff_matches_parsed_env": settings.kinsun_auth_handoff_secret
                == values.get("KINSUN_AUTH_HANDOFF_SECRET"),
                "identity_matches_parsed_env": settings.kinsun_identity_hmac_secret
                == values.get("KINSUN_IDENTITY_HMAC_SECRET"),
            }
        )
    )
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.post(
            "http://127.0.0.1:8000/api/v1/internal/auth/kinsun/password/login",
            headers={
                "X-Kinsun-BFF-Authorization": "Bearer "
                + settings.kinsun_auth_handoff_secret
            },
            json={},
        )
        print(
            json.dumps(
                {
                    "empty_body_handoff_probe": response.status_code,
                    "error_code": response.json().get("error", {}).get("code"),
                }
            )
        )
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.post(
            "http://127.0.0.1:8000/api/v1/internal/auth/kinsun/password/login",
            headers={
                "X-Kinsun-BFF-Authorization": "Bearer "
                + settings.kinsun_auth_handoff_secret
            },
            json=private["accounts"]["writer"],
        )
        print(
            json.dumps(
                {
                    "direct_synthetic_login": response.status_code,
                    "error_code": response.json().get("error", {}).get("code"),
                }
            )
        )
    codec = fixture.KinsunIdentityCodec(
        settings.kinsun_identity_hmac_secret, settings.kinsun_identity_hmac_key_version
    )
    hasher = fixture.PasswordHasher(
        fixture.Argon2idPolicy(
            parameter_version=settings.kinsun_password_parameter_version,
            memory_cost_kib=settings.kinsun_password_memory_cost_kib,
            iterations=settings.kinsun_password_iterations,
            lanes=settings.kinsun_password_lanes,
        )
    )
    engine = fixture.create_async_engine(
        settings.database_url, echo=False, hide_parameters=True
    )
    try:
        async with fixture.async_sessionmaker(engine)() as session:
            await session.execute(fixture.text("SET TRANSACTION READ ONLY"))
            result = []
            for who in ("writer", "reader"):
                identity = await session.get(
                    fixture.ExternalIdentity, fixture.IDS[who + "_identity"]
                )
                credential = await session.get(
                    fixture.PasswordCredential, fixture.IDS[who + "_credential"]
                )
                result.append(
                    {
                        "account": who,
                        "digest_matches": identity.external_subject_digest
                        == codec.digest_email(private["accounts"][who]["email"]),
                        "key_version_matches": identity.digest_key_version
                        == codec.key_version,
                        "password_matches": hasher.verify(
                            private["accounts"][who]["password"],
                            credential.password_hash,
                        ),
                        "failed_attempts": credential.failed_attempt_count,
                        "status": credential.status,
                    }
                )
            print(json.dumps(result))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
