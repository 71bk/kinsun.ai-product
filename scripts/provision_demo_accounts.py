"""Provision or reset deterministic local Demo login credentials without care-data reset."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_API_ROOT = REPO_ROOT / "services" / "core-api"
sys.path.insert(0, str(CORE_API_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.models.actor import Actor  # noqa: E402
from app.models.line_identity import ExternalIdentity  # noqa: E402
from app.models.password_credential import PasswordCredential  # noqa: E402
from app.services.kinsun_identity_codec import KinsunIdentityCodec  # noqa: E402
from app.services.password_hasher import Argon2idPolicy, PasswordHasher  # noqa: E402

EXPECTED_REVISION = "b8d0e4f6a213"
ALLOWED_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
DEMO_ACCOUNTS = (
    (
        "elder.demo@kinsun.local",
        UUID("20000000-0000-4000-8000-000000000001"),
        UUID("29000000-0000-4000-8000-000000000001"),
        UUID("2a000000-0000-4000-8000-000000000001"),
    ),
    (
        "staff.demo@kinsun.local",
        UUID("20000000-0000-4000-8000-000000000010"),
        UUID("29000000-0000-4000-8000-000000000010"),
        UUID("2a000000-0000-4000-8000-000000000010"),
    ),
    (
        "family.demo@kinsun.local",
        UUID("20000000-0000-4000-8000-000000000012"),
        UUID("29000000-0000-4000-8000-000000000012"),
        UUID("2a000000-0000-4000-8000-000000000012"),
    ),
)


def _load_repo_env() -> None:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _database_url() -> str:
    _load_repo_env()
    if os.getenv("APP_ENV", "development").lower() != "development":
        raise RuntimeError("Demo account provisioning is allowed only in development")
    value = os.getenv("DATABASE_URL", "")
    parsed = urlparse(value)
    database_name = parsed.path.removeprefix("/")
    hostname = parsed.hostname or ""
    local_target = hostname in ALLOWED_LOCAL_HOSTS and database_name == "kinsun"
    remote_opt_in = (
        os.getenv("KINSUN_ALLOW_REMOTE_DEMO_ACCOUNT_PROVISIONING", "false").lower()
        == "true"
    )
    supabase_target = (
        remote_opt_in
        and hostname.endswith(".supabase.com")
        and database_name == "postgres"
    )
    if (
        parsed.scheme != "postgresql+asyncpg"
        or not (local_target or supabase_target)
    ):
        raise RuntimeError(
            "Demo account provisioning requires local kinsun or an explicitly opted-in "
            "Supabase development database"
        )
    return value


async def _provision(session: AsyncSession) -> list[str]:
    revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
    if revision != EXPECTED_REVISION:
        raise RuntimeError(
            f"Database revision is {revision!r}; expected {EXPECTED_REVISION}. "
            "Run the additive migration before provisioning accounts."
        )
    settings = get_settings()
    if not settings.kinsun_native_auth_enabled:
        raise RuntimeError("KINSUN_NATIVE_AUTH_ENABLED must be true")
    password = os.getenv("DEMO_ACCOUNT_PASSWORD", "")
    if not password:
        raise RuntimeError("DEMO_ACCOUNT_PASSWORD is required")
    identity_codec = KinsunIdentityCodec(
        settings.kinsun_identity_hmac_secret,
        settings.kinsun_identity_hmac_key_version,
    )
    password_hasher = PasswordHasher(
        Argon2idPolicy(
            parameter_version=settings.kinsun_password_parameter_version,
            memory_cost_kib=settings.kinsun_password_memory_cost_kib,
            iterations=settings.kinsun_password_iterations,
            lanes=settings.kinsun_password_lanes,
        )
    )
    now = datetime.now(UTC)
    emails: list[str] = []
    for email, actor_id, identity_id, credential_id in DEMO_ACCOUNTS:
        actor = await session.get(Actor, actor_id, with_for_update=True)
        if actor is None:
            raise RuntimeError(f"Demo actor {actor_id} is missing; run scripts/reset_demo.ps1")
        normalized_email = identity_codec.normalize_email(email)
        if actor.email not in {None, normalized_email}:
            raise RuntimeError(f"Demo actor {actor_id} already has a different email")
        subject_digest = identity_codec.digest_email(normalized_email)
        identity = await session.scalar(
            select(ExternalIdentity)
            .where(
                ExternalIdentity.provider == "KINSUN",
                ExternalIdentity.external_subject_digest == subject_digest,
                ExternalIdentity.digest_key_version == identity_codec.key_version,
            )
            .with_for_update()
        )
        if identity is None:
            identity = ExternalIdentity(
                id=identity_id,
                provider="KINSUN",
                external_subject_digest=subject_digest,
                digest_key_version=identity_codec.key_version,
                actor_id=actor.id,
                status="ACTIVE",
                linked_at=now,
                version=1,
            )
            session.add(identity)
        elif identity.actor_id != actor.id:
            raise RuntimeError("Demo email is already linked to another actor")
        else:
            identity.status = "ACTIVE"
            identity.revoked_at = None
            identity.version = (identity.version or 0) + 1

        credential = await session.scalar(
            select(PasswordCredential)
            .where(PasswordCredential.actor_id == actor.id)
            .with_for_update()
        )
        password_hash = password_hasher.hash(password)
        if credential is None:
            session.add(
                PasswordCredential(
                    id=credential_id,
                    actor_id=actor.id,
                    password_hash=password_hash,
                    algorithm="ARGON2ID",
                    parameter_version=password_hasher.policy.parameter_version,
                    status="ACTIVE",
                    failed_attempt_count=0,
                    locked_until=None,
                    password_changed_at=now,
                    last_verified_at=None,
                    revoked_at=None,
                    version=1,
                )
            )
        else:
            credential.password_hash = password_hash
            credential.algorithm = "ARGON2ID"
            credential.parameter_version = password_hasher.policy.parameter_version
            credential.status = "ACTIVE"
            credential.failed_attempt_count = 0
            credential.locked_until = None
            credential.password_changed_at = now
            credential.revoked_at = None
            credential.version = (credential.version or 0) + 1
        actor.email = normalized_email
        emails.append(normalized_email)
    await session.flush()
    return emails


async def main() -> None:
    engine = create_async_engine(_database_url())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            async with session.begin():
                emails = await _provision(session)
    finally:
        await engine.dispose()
    print(json.dumps({"ok": True, "demo_accounts": emails}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
