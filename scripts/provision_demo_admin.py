"""Create a separate development admin without resetting any existing account."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import UUID

from provision_demo_accounts import (
    _database_url,
    _repository_head_revision,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bootstrap.dependencies import get_kinsun_identity_codec, get_password_hasher
from app.core.config import get_settings
from app.models.actor import Actor
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.password_credential import PasswordCredential
from app.models.tenant import Tenant
from app.repositories.kinsun_identity_repo import KinsunIdentityRepository
from app.schemas.kinsun_email_auth import PasswordLoginRequest
from app.services.actor_context_resolver import resolve_active_actor_context

EMAIL = "admin.demo@kinsun.local"
ACTOR_ID = UUID("20000000-0000-4000-8000-000000000090")
TENANT_ID = UUID("10000000-0000-4000-8000-000000000001")


async def provision(session) -> bool:
    if not get_settings().kinsun_native_auth_enabled:
        raise RuntimeError("KINSUN_NATIVE_AUTH_ENABLED must be true")
    revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
    if revision != _repository_head_revision():
        raise RuntimeError("Apply the additive Core migration before provisioning")
    request = PasswordLoginRequest(email=EMAIL, password=os.getenv("DEMO_ACCOUNT_PASSWORD", ""))
    codec = get_kinsun_identity_codec()
    hasher = get_password_hasher()
    digest = codec.digest_email(EMAIL)
    identities = KinsunIdentityRepository(session)
    await identities.acquire_subject_lock(subject_digest=digest, key_version=codec.key_version)
    existing = await identities.list_identities_by_subject(
        subject_digest=digest, key_version=codec.key_version
    )
    actor = await session.get(Actor, ACTOR_ID)
    if existing or actor:
        if (
            len(existing) != 1
            or actor is None
            or existing[0].actor_id != ACTOR_ID
            or existing[0].status != "ACTIVE"
            or actor.actor_type != "ADMIN"
            or actor.email != EMAIL
        ):
            raise RuntimeError("Existing identity differs; refusing to alter privileges")
        context = await resolve_active_actor_context(session, actor)
        credential = await session.scalar(
            select(PasswordCredential).where(
                PasswordCredential.actor_id == ACTOR_ID,
                PasswordCredential.status == "ACTIVE",
            )
        )
        if context.tenant_id != TENANT_ID or credential is None:
            raise RuntimeError("Existing admin is incompatible; no changes made")
        return False
    tenant = await session.get(Tenant, TENANT_ID)
    if tenant is None or tenant.status != "ACTIVE":
        raise RuntimeError("Active demo tenant is required; no data reset will be performed")
    now = datetime.now(UTC)
    session.add(
        Actor(
            id=ACTOR_ID,
            actor_type="ADMIN",
            display_name="Demo Administrator",
            email=EMAIL,
            status="ACTIVE",
        )
    )
    await session.flush()
    session.add_all(
        [
            ExternalIdentity(
                provider="KINSUN",
                external_subject_digest=digest,
                digest_key_version=codec.key_version,
                actor_id=ACTOR_ID,
                status="ACTIVE",
                linked_at=now,
                version=1,
            ),
            PasswordCredential(
                actor_id=ACTOR_ID,
                password_hash=hasher.hash(request.password.get_secret_value()),
                algorithm="ARGON2ID",
                parameter_version=hasher.policy.parameter_version,
                status="ACTIVE",
                failed_attempt_count=0,
                password_changed_at=now,
                version=1,
            ),
            ActorTenantMembership(
                actor_id=ACTOR_ID,
                tenant_id=TENANT_ID,
                care_unit_id=None,
                role_code="ADMIN",
                status="ACTIVE",
                effective_from=now,
            ),
        ]
    )
    await session.flush()
    return True


async def main() -> None:
    engine = create_async_engine(_database_url(), hide_parameters=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            async with session.begin():
                created = await provision(session)
    finally:
        await engine.dispose()
    print(json.dumps({"ok": True, "created": created, "email": EMAIL, "role": "ADMIN"}))


if __name__ == "__main__":
    asyncio.run(main())
