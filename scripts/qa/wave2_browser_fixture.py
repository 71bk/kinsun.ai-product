"""Bounded synthetic fixture for manual, real-auth Wave 2 browser acceptance.

Default is read-only inspection. Writes require an explicit CLI opt-in, a
development Supabase target and the existing synthetic staff identity. No reset,
delete, credential changes or changes to existing demo relationships are offered.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/core-api"))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.models.actor import Actor  # noqa: E402
from app.models.care_action import CareAction  # noqa: E402
from app.models.care_action_candidate import CareActionCandidate  # noqa: E402
from app.models.care_event import CareEvent, CareEventVersion  # noqa: E402
from app.models.care_relationship import CareRelationship  # noqa: E402
from app.models.care_unit import CareUnit  # noqa: E402
from app.models.elder import Elder  # noqa: E402
from app.models.idempotency import IdempotencyRecord  # noqa: E402
from app.models.membership import ActorTenantMembership  # noqa: E402
from app.models.outbox import OutboxEvent  # noqa: E402
from app.services.care_action_candidate_service import CareActionCandidateService  # noqa: E402

RUN = "wave2-browser-20260907"
MARKER = "Synthetic Wave2 E2E 20260907"
STAFF = UUID("20000000-0000-4000-8000-000000000010")
TENANT = UUID("10000000-0000-4000-8000-000000000001")
IDS = {
    name: uuid5(NAMESPACE_URL, f"kinsun:{RUN}:{name}")
    for name in ("unit", "membership", "elder", "unassigned", "relationship")
}
SCOPES = [
    "elder:basic:read",
    "elder:access_context:read",
    "care_event:read",
    "care_action:read",
    "care_action:create",
    "care_action:update",
    "summary:read",
]


def validate_command(command: str, allow_write: bool) -> None:
    if command not in {"inspect", "prepare", "expire"}:
        raise RuntimeError("Unknown fixture command")
    if command != "inspect" and not allow_write:
        raise RuntimeError("Explicit --allow-synthetic-write is required")


def validate_target(app_env: str, database_url: str) -> None:
    target = urlsplit(database_url)
    if app_env != "development" or not (
        target.scheme == "postgresql+asyncpg"
        and (target.hostname or "").endswith(".supabase.com")
        and target.path == "/postgres"
    ):
        raise RuntimeError("Only the configured Supabase development target is allowed")


async def assert_owner(session):
    actor = await session.get(Actor, STAFF)
    if (
        actor is None
        or actor.actor_type != "DAYCARE_CARE_WORKER"
        or actor.status != "ACTIVE"
    ):
        raise RuntimeError("Synthetic staff identity is unavailable")
    now = datetime.now(UTC)
    membership = await session.scalar(
        select(ActorTenantMembership).where(
            ActorTenantMembership.actor_id == STAFF,
            ActorTenantMembership.tenant_id == TENANT,
            ActorTenantMembership.care_unit_id.is_(None),
            ActorTenantMembership.status == "ACTIVE",
            ActorTenantMembership.role_code == "DAYCARE_CARE_WORKER",
            ActorTenantMembership.effective_from <= now,
            (ActorTenantMembership.effective_to.is_(None))
            | (ActorTenantMembership.effective_to > now),
        )
    )
    if membership is None:
        raise RuntimeError("Synthetic tenant membership is unavailable")


async def prepare(session):
    await assert_owner(session)
    # Deterministic IDs permit exact inspection and expiry without broad queries.
    if any(
        [
            await session.get(model, IDS[key]) is not None
            for model, key in (
                (CareUnit, "unit"),
                (ActorTenantMembership, "membership"),
                (Elder, "elder"),
                (Elder, "unassigned"),
                (CareRelationship, "relationship"),
            )
        ]
    ):
        raise RuntimeError("Fixture already exists; inspect it, do not overwrite it")
    now = datetime.now(UTC)
    expiry = now + timedelta(hours=4)
    session.add(
        CareUnit(
            id=IDS["unit"], tenant_id=TENANT, unit_type="DAYCARE_CENTER", name=MARKER
        )
    )
    await session.flush()
    session.add_all(
        [
            Elder(
                id=IDS[key],
                tenant_id=TENANT,
                primary_care_unit_id=IDS["unit"],
                display_name=f"{MARKER} {key}",
                primary_care_setting="DAYCARE",
            )
            for key in ("elder", "unassigned")
        ]
    )
    session.add(
        ActorTenantMembership(
            id=IDS["membership"],
            actor_id=STAFF,
            tenant_id=TENANT,
            care_unit_id=IDS["unit"],
            role_code="DAYCARE_CARE_WORKER",
            status="ACTIVE",
            effective_from=now - timedelta(minutes=1),
            effective_to=expiry,
        )
    )
    await session.flush()
    session.add(
        CareRelationship(
            id=IDS["relationship"],
            tenant_id=TENANT,
            elder_id=IDS["elder"],
            actor_id=STAFF,
            care_unit_id=IDS["unit"],
            relationship_type="DAYCARE_ASSIGNMENT",
            scope=SCOPES,
            status="ACTIVE",
            effective_from=now - timedelta(minutes=1),
            effective_to=expiry,
        )
    )
    for label in ("Adopt", "Reject", "Exclude"):
        event = CareEvent(
            id=uuid5(NAMESPACE_URL, f"kinsun:{RUN}:event:{label}"),
            tenant_id=TENANT,
            elder_id=IDS["elder"],
            event_type="EXPECTED_CONTACT_MISSED",
            status="VERIFIED",
            event_time=now,
            current_version=1,
            consent_version=1,
        )
        session.add(event)
        await session.flush()
        version = CareEventVersion(
            event_id=event.id,
            version=1,
            structured_payload={
                "summary": f"{MARKER} {label} source; synthetic fixture, not live AI"
            },
            evidence_text_ref='["synthetic:wave2-browser-e2e"]',
            created_by_actor_id=STAFF,
        )
        session.add(version)
        await session.flush()
        await CareActionCandidateService(session, TENANT).create_from_verified_event(
            event=event,
            event_version=version,
            proposal_payload={
                "action_type": "CONTACT_ELDER",
                "suggested_title": f"{MARKER} {label}",
                "trigger_reason": "Synthetic missed contact; non-medical browser acceptance",
                "suggested_due_at": (now + timedelta(days=2)).isoformat(),
                "priority": "MEDIUM",
                "extractor_version": "synthetic-browser-fixture.v1",
            },
        )


async def expire(session):
    unit = await session.get(CareUnit, IDS["unit"])
    elder = await session.get(Elder, IDS["elder"])
    relation = await session.get(
        CareRelationship, IDS["relationship"], with_for_update=True
    )
    membership = await session.get(
        ActorTenantMembership, IDS["membership"], with_for_update=True
    )
    if not (
        unit
        and unit.name == MARKER
        and unit.tenant_id == TENANT
        and elder
        and elder.display_name == f"{MARKER} elder"
        and elder.tenant_id == TENANT
        and elder.primary_care_unit_id == IDS["unit"]
        and relation
        and membership
        and relation.elder_id == IDS["elder"]
        and relation.actor_id == STAFF
        and relation.care_unit_id == membership.care_unit_id == IDS["unit"]
        and relation.tenant_id == membership.tenant_id == TENANT
        and membership.actor_id == STAFF
        and membership.role_code == "DAYCARE_CARE_WORKER"
        and relation.relationship_type == "DAYCARE_ASSIGNMENT"
    ):
        raise RuntimeError("Fixture ownership mismatch; refusing expiry")
    cutoff = datetime.now(UTC) - timedelta(seconds=1)
    for authorization in (relation, membership):
        # Re-running expiry must never extend an already expired authorization.
        authorization.effective_to = min(authorization.effective_to or cutoff, cutoff)


async def inspect_state(session):
    states = {}
    for model in (CareAction, CareActionCandidate, OutboxEvent):
        rows = (
            (
                await session.execute(
                    select(model.__table__)
                    .where(model.tenant_id == TENANT, model.elder_id == IDS["elder"])
                    .order_by(*model.__table__.primary_key)
                )
            )
            .mappings()
            .all()
        )
        states[model.__tablename__] = [dict(row) for row in rows]
    resource_ids = [row["care_action_id"] for row in states["care_action"]] + [
        row["care_action_candidate_id"] for row in states["care_action_candidate"]
    ]
    claims = (
        (
            await session.execute(
                select(IdempotencyRecord.__table__)
                .where(
                    IdempotencyRecord.tenant_id == TENANT,
                    IdempotencyRecord.actor_id == STAFF,
                    IdempotencyRecord.resource_id.in_(resource_ids),
                )
                .order_by(IdempotencyRecord.idempotency_key)
            )
        )
        .mappings()
        .all()
    )
    states["claims"] = [dict(row) for row in claims]
    digest = hashlib.sha256(
        json.dumps(states, sort_keys=True, default=str).encode()
    ).hexdigest()
    relation = await session.get(CareRelationship, IDS["relationship"])
    return {
        "run": RUN,
        "ids": IDS,
        "state_sha256": digest,
        "expires_at": relation.effective_to if relation else None,
        "counts": {key: len(rows) for key, rows in states.items()},
        "actions": [
            {
                key: row[key]
                for key in (
                    "care_action_id",
                    "title",
                    "status",
                    "version",
                    "resolution",
                )
            }
            for row in states["care_action"]
        ],
        "candidates": [
            {
                key: row[key]
                for key in (
                    "care_action_candidate_id",
                    "suggested_title",
                    "status",
                    "version",
                    "adopted_care_action_id",
                    "disposition_reason_code",
                )
            }
            for row in states["care_action_candidate"]
        ],
        "outbox": [
            {
                key: row[key]
                for key in ("event_type", "aggregate_id", "aggregate_version")
            }
            for row in states["outbox_event"]
        ],
    }


async def main(args):
    validate_command(args.command, args.allow_synthetic_write)
    settings = Settings(_env_file=ROOT / ".env")
    validate_target(settings.app_env.value, settings.database_url)
    engine = create_async_engine(
        settings.database_url, echo=False, hide_parameters=True
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            async with session.begin():
                if args.command == "inspect":
                    await session.execute(text("SET TRANSACTION READ ONLY"))
                elif args.command == "prepare":
                    await prepare(session)
                else:
                    await expire(session)
            async with session.begin():
                await session.execute(text("SET TRANSACTION READ ONLY"))
                result = await inspect_state(session)
                print(json.dumps(result, default=str))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("inspect", "prepare", "expire"),
        default="inspect",
        nargs="?",
    )
    parser.add_argument("--allow-synthetic-write", action="store_true")
    try:
        asyncio.run(main(parser.parse_args()))
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__, "ok": False}))
        raise SystemExit(1) from None
