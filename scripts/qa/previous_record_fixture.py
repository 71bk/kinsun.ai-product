"""Opt-in, isolated development fixture; never resets or edits existing users."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api"))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.models.actor import Actor  # noqa: E402
from app.models.app_session import AppSession  # noqa: E402
from app.models.care_assignment import CareAssignment  # noqa: E402
from app.models.care_unit import CareUnit  # noqa: E402
from app.models.elder import Elder  # noqa: E402
from app.models.line_identity import ExternalIdentity  # noqa: E402
from app.models.membership import ActorTenantMembership  # noqa: E402
from app.models.outbox import OutboxEvent  # noqa: E402
from app.models.password_credential import PasswordCredential  # noqa: E402
from app.models.service_record import ServiceRecord  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.services.kinsun_identity_codec import KinsunIdentityCodec  # noqa: E402
from app.services.password_hasher import Argon2idPolicy, PasswordHasher  # noqa: E402

CAMPAIGN = "previous-record-real-auth-20260914"
MARKER = "Synthetic Previous Record 20260914"
KEYS = (
    "tenant",
    "foreign_tenant",
    "unit",
    "foreign_unit",
    "elder",
    "foreign_elder",
    "writer",
    "reader",
    "writer_identity",
    "reader_identity",
    "writer_credential",
    "reader_credential",
    "writer_membership",
    "reader_membership",
    "writer_login_membership",
    "reader_login_membership",
    "source",
    "source_note",
    "current",
    "expiry",
    "no_history",
    "writer_current",
    "foreign_assignment",
)
IDS = {key: uuid5(NAMESPACE_URL, f"kinsun:{CAMPAIGN}:{key}") for key in KEYS}
PRIVATE = ROOT / ".qa/.env.previous-record-real-auth"
NOTE = "Synthetic handover fixture 20260914: completed a planned activity. Human-authored test source, not live care data."
SCOPES = [
    "assignment:read",
    "elder:basic:read",
    "elder:access_context:read",
    "service_record:read",
    "service_record:write",
    "service_record:history:read",
    "assignment:complete",
]


def validate_target(app_env, database_url):
    target = urlsplit(database_url)
    if app_env != "development" or not (
        target.scheme == "postgresql+asyncpg"
        and (target.hostname or "").endswith(".supabase.com")
        and target.path == "/postgres"
    ):
        raise RuntimeError("Development Supabase target required")


def validate_command(command, allow_write):
    if command not in {
        "inspect",
        "prepare",
        "add-login-memberships",
        "expire-reader",
        "retire",
    }:
        raise RuntimeError("Unsupported command")
    if command != "inspect" and not allow_write:
        raise RuntimeError("Explicit synthetic-write opt-in required")


async def prepare(session, settings):
    if await session.get(Tenant, IDS["tenant"]) or PRIVATE.exists():
        raise RuntimeError("Campaign exists; inspect or retire, never overwrite")
    now = datetime.now(UTC)
    end = now + timedelta(hours=4)
    passwords = {who: secrets.token_urlsafe(32) for who in ("writer", "reader")}
    codec = KinsunIdentityCodec(
        settings.kinsun_identity_hmac_secret, settings.kinsun_identity_hmac_key_version
    )
    hasher = PasswordHasher(
        Argon2idPolicy(
            parameter_version=settings.kinsun_password_parameter_version,
            memory_cost_kib=settings.kinsun_password_memory_cost_kib,
            iterations=settings.kinsun_password_iterations,
            lanes=settings.kinsun_password_lanes,
        )
    )
    for prefix in ("", "foreign_"):
        session.add(
            Tenant(id=IDS[prefix + "tenant"], tenant_type="DEMO", name=MARKER + prefix)
        )
    for who in passwords:
        session.add(
            Actor(
                id=IDS[who],
                actor_type="HOME_CARE_WORKER",
                display_name=MARKER + " " + who,
            )
        )
    await session.flush()
    for prefix in ("", "foreign_"):
        session.add(
            CareUnit(
                id=IDS[prefix + "unit"],
                tenant_id=IDS[prefix + "tenant"],
                unit_type="HOME_CARE_AGENCY",
                name=MARKER + prefix,
            )
        )
    await session.flush()
    for prefix in ("", "foreign_"):
        session.add(
            Elder(
                id=IDS[prefix + "elder"],
                tenant_id=IDS[prefix + "tenant"],
                primary_care_unit_id=IDS[prefix + "unit"],
                primary_care_setting="HOME_CARE",
                display_name=MARKER + prefix,
            )
        )
    for who, password in passwords.items():
        email = f"{who}.{CAMPAIGN}@example.invalid"
        session.add(
            ExternalIdentity(
                id=IDS[who + "_identity"],
                provider="KINSUN",
                actor_id=IDS[who],
                external_subject_digest=codec.digest_email(email),
                digest_key_version=codec.key_version,
                status="ACTIVE",
                version=1,
            )
        )
        session.add(
            PasswordCredential(
                id=IDS[who + "_credential"],
                actor_id=IDS[who],
                password_hash=hasher.hash(password),
                parameter_version=hasher.policy.parameter_version,
                version=1,
            )
        )
        session.add(
            ActorTenantMembership(
                id=IDS[who + "_membership"],
                actor_id=IDS[who],
                tenant_id=IDS["tenant"],
                care_unit_id=IDS["unit"],
                role_code="HOME_CARE_WORKER",
                effective_from=now - timedelta(days=1),
                effective_to=end,
            )
        )
    await session.flush()
    await add_login_memberships(session)
    for index, key in enumerate(
        (
            "source",
            "current",
            "expiry",
            "no_history",
            "writer_current",
            "foreign_assignment",
        )
    ):
        historical = key == "source"
        prefix = "foreign_" if key == "foreign_assignment" else ""
        start = (
            now - timedelta(days=1, hours=2)
            if historical
            else now - timedelta(minutes=30 - index)
        )
        finish = now - timedelta(days=1) if historical else end
        who = "writer" if key in {"source", "writer_current"} else "reader"
        scopes = (
            []
            if historical
            else [
                scope
                for scope in SCOPES
                if key != "no_history" or scope != "service_record:history:read"
            ]
        )
        session.add(
            CareAssignment(
                id=IDS[key],
                tenant_id=IDS[prefix + "tenant"],
                elder_id=IDS[prefix + "elder"],
                care_unit_id=IDS[prefix + "unit"],
                worker_id=IDS[who],
                service_start=start,
                service_end=finish,
                status="COMPLETED" if historical else "IN_PROGRESS",
                service_scope=scopes,
                version=3 if historical else 2,
            )
        )
    await session.flush()
    source = await session.get(CareAssignment, IDS["source"])
    session.add(
        ServiceRecord(
            service_record_id=IDS["source_note"],
            assignment_id=source.id,
            tenant_id=source.tenant_id,
            elder_id=source.elder_id,
            worker_id=source.worker_id,
            service_date=source.service_start.astimezone(
                ZoneInfo("Asia/Taipei")
            ).date(),
            service_timezone="Asia/Taipei",
            record_type="SERVICE_NOTE",
            content={"note": NOTE},
            status="COMPLETED",
            version=1,
            assignment_version=2,
            completed_at=source.service_start + timedelta(hours=1),
        )
    )
    await session.flush()
    # A private, git-ignored bootstrap file; never contains an App Session token.
    with PRIVATE.open("x", encoding="utf-8") as handle:
        json.dump(
            {
                "campaign": CAMPAIGN,
                "ids": {k: str(v) for k, v in IDS.items()},
                "expires_at": end.isoformat(),
                "accounts": {
                    who: {
                        "email": f"{who}.{CAMPAIGN}@example.invalid",
                        "password": password,
                    }
                    for who, password in passwords.items()
                },
            },
            handle,
        )


async def add_login_memberships(session):
    """Add the separate login gate once, bounded by existing campaign expiry."""
    tenant = await session.get(Tenant, IDS["tenant"])
    if tenant is None or tenant.name != MARKER:
        raise RuntimeError("Campaign ownership mismatch")
    now = datetime.now(UTC)
    for who in ("writer", "reader"):
        actor = await session.get(Actor, IDS[who])
        unit_membership = await session.get(
            ActorTenantMembership, IDS[who + "_membership"]
        )
        existing = await session.get(
            ActorTenantMembership, IDS[who + "_login_membership"]
        )
        if not (
            actor
            and actor.display_name == MARKER + " " + who
            and actor.actor_type == "HOME_CARE_WORKER"
            and actor.status == "ACTIVE"
            and unit_membership
            and unit_membership.actor_id == actor.id
            and unit_membership.tenant_id == tenant.id
            and unit_membership.care_unit_id == IDS["unit"]
            and unit_membership.role_code == "HOME_CARE_WORKER"
            and unit_membership.effective_from < now < unit_membership.effective_to
            and existing is None
        ):
            raise RuntimeError("Login membership ownership mismatch or already exists")
        session.add(
            ActorTenantMembership(
                id=IDS[who + "_login_membership"],
                actor_id=actor.id,
                tenant_id=tenant.id,
                care_unit_id=None,
                role_code="HOME_CARE_WORKER",
                effective_from=now,
                effective_to=unit_membership.effective_to,
            )
        )
    await session.flush()


async def retire(session, reader_only=False):
    tenant = await session.get(Tenant, IDS["tenant"])
    if tenant is None or tenant.name != MARKER:
        raise RuntimeError("Campaign ownership mismatch")
    now = datetime.now(UTC)
    for who in ("reader",) if reader_only else ("writer", "reader"):
        actor = await session.get(Actor, IDS[who], with_for_update=True)
        membership = await session.get(
            ActorTenantMembership, IDS[who + "_membership"], with_for_update=True
        )
        if not (
            actor
            and actor.display_name == MARKER + " " + who
            and membership
            and membership.actor_id == actor.id
            and membership.tenant_id == tenant.id
            and membership.care_unit_id == IDS["unit"]
            and membership.effective_from < now
        ):
            raise RuntimeError("Authorization ownership mismatch")
        membership.effective_to = min(membership.effective_to, now)
        login_membership = await session.get(
            ActorTenantMembership, IDS[who + "_login_membership"], with_for_update=True
        )
        if login_membership is not None:
            if not (
                login_membership.actor_id == actor.id
                and login_membership.tenant_id == tenant.id
                and login_membership.care_unit_id is None
                and login_membership.role_code == "HOME_CARE_WORKER"
                and login_membership.effective_from < now
            ):
                raise RuntimeError("Login membership ownership mismatch")
            login_membership.effective_to = min(login_membership.effective_to, now)
        if reader_only:
            continue
        actor.status = "INACTIVE"
        credential = await session.get(
            PasswordCredential, IDS[who + "_credential"], with_for_update=True
        )
        identity = await session.get(
            ExternalIdentity, IDS[who + "_identity"], with_for_update=True
        )
        if not (
            credential
            and identity
            and credential.actor_id == actor.id
            and identity.actor_id == actor.id
            and identity.provider == "KINSUN"
        ):
            raise RuntimeError("Credential ownership mismatch")
        credential.status, credential.revoked_at, credential.locked_until = (
            "REVOKED",
            now,
            None,
        )
        credential.version += 1
        identity.status, identity.revoked_at = "REVOKED", now
        identity.version += 1
        sessions = (
            await session.scalars(
                select(AppSession)
                .where(AppSession.actor_id == actor.id, AppSession.status == "ACTIVE")
                .with_for_update()
            )
        ).all()
        for row in sessions:
            row.status, row.revoked_at = "REVOKED", max(now, row.authenticated_at)
            row.version += 1


async def inspect(session):
    now = datetime.now(UTC)
    notes = (
        await session.scalars(
            select(ServiceRecord)
            .where(ServiceRecord.tenant_id.in_([IDS["tenant"], IDS["foreign_tenant"]]))
            .order_by(ServiceRecord.service_record_id)
        )
    ).all()
    events = (
        await session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.tenant_id.in_([IDS["tenant"], IDS["foreign_tenant"]]))
            .order_by(OutboxEvent.event_id)
        )
    ).all()
    memberships = (
        await session.scalars(
            select(ActorTenantMembership).where(
                ActorTenantMembership.id.in_(
                    [
                        IDS[key]
                        for key in (
                            "writer_membership",
                            "reader_membership",
                            "writer_login_membership",
                            "reader_login_membership",
                        )
                    ]
                )
            )
        )
    ).all()
    credentials = (
        await session.scalars(
            select(PasswordCredential).where(
                PasswordCredential.actor_id.in_([IDS["reader"], IDS["writer"]])
            )
        )
    ).all()
    sessions = (
        await session.scalars(
            select(AppSession).where(
                AppSession.actor_id.in_([IDS["reader"], IDS["writer"]])
            )
        )
    ).all()
    assignments = (
        await session.scalars(
            select(CareAssignment)
            .where(
                CareAssignment.id.in_(
                    [
                        IDS[k]
                        for k in (
                            "source",
                            "current",
                            "expiry",
                            "no_history",
                            "writer_current",
                            "foreign_assignment",
                        )
                    ]
                )
            )
            .order_by(CareAssignment.id)
        )
    ).all()
    snapshots = [
        {col.key: getattr(row, col.key) for col in type(row).__mapper__.column_attrs}
        for row in [*notes, *events]
    ]
    return {
        "campaign": CAMPAIGN,
        "revision": (
            await session.execute(
                text("SELECT version_num FROM public.alembic_version")
            )
        ).scalar_one(),
        "prepared": bool(await session.get(Tenant, IDS["tenant"])),
        "notes": len(notes),
        "outbox": len(events),
        "outbox_events": [
            {
                "id": str(row.event_id),
                "type": row.event_type,
                "aggregate": str(row.aggregate_id),
            }
            for row in events
        ],
        "source_note_sha256": hashlib.sha256(
            json.dumps(
                [
                    snapshot
                    for row, snapshot in zip([*notes, *events], snapshots, strict=True)
                    if isinstance(row, ServiceRecord)
                    and row.service_record_id == IDS["source_note"]
                ],
                default=str,
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        "records": [
            {
                "id": str(row.service_record_id),
                "assignment": str(row.assignment_id),
                "worker": str(row.worker_id),
                "version": row.version,
            }
            for row in notes
        ],
        "assignments": [
            {"id": str(row.id), "status": row.status, "version": row.version}
            for row in assignments
        ],
        "live_memberships": sum(
            row.effective_from <= now < row.effective_to for row in memberships
        ),
        "active_credentials": sum(row.status == "ACTIVE" for row in credentials),
        "active_sessions": sum(row.status == "ACTIVE" for row in sessions),
        "record_outbox_sha256": hashlib.sha256(
            json.dumps(snapshots, default=str, sort_keys=True).encode()
        ).hexdigest(),
    }


async def run(command, allow_write):
    validate_command(command, allow_write)
    settings = Settings(_env_file=ROOT / ".env")
    validate_target(settings.app_env, settings.database_url)
    if (
        not settings.kinsun_native_auth_enabled
        or not settings.app_session_auth_enabled
        or settings.fake_auth_enabled
    ):
        raise RuntimeError(
            "Real native authentication must be enabled without fake auth"
        )
    engine = create_async_engine(
        settings.database_url, echo=False, hide_parameters=True
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            async with session.begin():
                if command == "inspect":
                    await session.execute(text("SET TRANSACTION READ ONLY"))
                if command == "prepare":
                    await prepare(session, settings)
                elif command == "add-login-memberships":
                    await add_login_memberships(session)
                elif command in {"expire-reader", "retire"}:
                    await retire(session, reader_only=command == "expire-reader")
                await session.flush()
                result = await inspect(session)
        if command == "retire" and PRIVATE.exists():
            PRIVATE.write_text(
                json.dumps(
                    {
                        "campaign": CAMPAIGN,
                        "retired": True,
                        "ids": {k: str(v) for k, v in IDS.items()},
                    }
                ),
                encoding="utf-8",
            )
        print(json.dumps(result))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            "inspect",
            "prepare",
            "add-login-memberships",
            "expire-reader",
            "retire",
        ],
        nargs="?",
        default="inspect",
    )
    parser.add_argument("--allow-synthetic-write", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.command, args.allow_synthetic_write))
    except Exception as error:
        print(json.dumps({"result": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
