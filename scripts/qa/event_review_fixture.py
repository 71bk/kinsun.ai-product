"""Opt-in, isolated B03/B04 development campaign; no resets or existing-user edits."""

# ruff: noqa: E402 -- standalone tool adds the Core source root before imports.

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api"))
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database_url import to_psycopg_database_url
from app.models.actor import Actor
from app.models.app_session import AppSession
from app.models.care_event import CareEvent, CareEventVersion, ReviewDecision
from app.models.care_relationship import CareRelationship
from app.models.care_unit import CareUnit
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.models.line_identity import ExternalIdentity
from app.models.membership import ActorTenantMembership
from app.models.outbox import OutboxEvent
from app.models.password_credential import PasswordCredential
from app.models.policy import PolicyRegistry
from app.models.tenant import Tenant
from app.services.kinsun_identity_codec import KinsunIdentityCodec
from app.services.password_hasher import Argon2idPolicy, PasswordHasher

CAMPAIGN = "b03-b04-real-auth-20260916"
MARKER = "Synthetic B03 B04 20260916"
ROLE = "DAYCARE_CARE_WORKER"
IDS = {
    k: uuid5(NAMESPACE_URL, f"kinsun:{CAMPAIGN}:{k}")
    for k in (
        "tenant",
        "unit",
        "elder",
        "unassigned",
        "worker",
        "identity",
        "credential",
        "login_membership",
        "unit_membership",
        "relationship",
        "policy",
        "consent",
        "conversation",
        "legacy_unknown",
        "legacy_conversation",
    )
}
PRIVATE = ROOT / ".qa/.env.b03-b04-real-auth"
SCOPES = [
    "elder:basic:read",
    "elder:access_context:read",
    "care_event:read",
    "care_event:review",
    "care_event:candidate:create",
]


def validate_target(settings):
    url = make_url(settings.database_url)
    if not (
        settings.app_env == "development"
        and url.drivername == "postgresql+asyncpg"
        and (url.host or "").endswith(".supabase.com")
        and url.database == "postgres"
        and settings.kinsun_native_auth_enabled
        and settings.app_session_auth_enabled
        and not settings.fake_auth_enabled
    ):
        raise RuntimeError("Real-auth development Supabase required")


def prepare(session, settings):
    if PRIVATE.exists() or session.get(Tenant, IDS["tenant"]):
        raise RuntimeError("Campaign exists; never overwrite or renew")
    now = datetime.now(UTC)
    end = now + timedelta(hours=2)
    password = secrets.token_urlsafe(32)
    email = f"worker.{CAMPAIGN}@example.invalid"
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
    session.add_all(
        [
            Tenant(id=IDS["tenant"], tenant_type="DEMO", name=MARKER),
            Actor(id=IDS["worker"], actor_type=ROLE, display_name=MARKER + " worker"),
        ]
    )
    session.flush()
    session.add(
        CareUnit(
            id=IDS["unit"],
            tenant_id=IDS["tenant"],
            unit_type="DAYCARE_CENTER",
            name=MARKER,
        )
    )
    session.flush()
    for key in ("elder", "unassigned"):
        session.add(
            Elder(
                id=IDS[key],
                tenant_id=IDS["tenant"],
                primary_care_unit_id=IDS["unit"],
                primary_care_setting="DAYCARE",
                display_name=MARKER + " " + key,
            )
        )
    session.add(
        ExternalIdentity(
            id=IDS["identity"],
            provider="KINSUN",
            actor_id=IDS["worker"],
            external_subject_digest=codec.digest_email(email),
            digest_key_version=codec.key_version,
            status="ACTIVE",
            version=1,
        )
    )
    session.add(
        PasswordCredential(
            id=IDS["credential"],
            actor_id=IDS["worker"],
            password_hash=hasher.hash(password),
            parameter_version=hasher.policy.parameter_version,
            version=1,
        )
    )
    for key, unit in [("login_membership", None), ("unit_membership", IDS["unit"])]:
        session.add(
            ActorTenantMembership(
                id=IDS[key],
                actor_id=IDS["worker"],
                tenant_id=IDS["tenant"],
                care_unit_id=unit,
                role_code=ROLE,
                effective_from=now - timedelta(minutes=1),
                effective_to=end,
            )
        )
    session.add(
        PolicyRegistry(
            id=IDS["policy"],
            owner_tenant_id=IDS["tenant"],
            policy_code=CAMPAIGN,
            policy_type="CONSENT",
            version="synthetic-v1",
            status="ACTIVE",
            policy_payload={"synthetic": True},
            effective_from=now - timedelta(minutes=1),
            effective_to=end,
        )
    )
    session.flush()
    session.add(
        CareRelationship(
            id=IDS["relationship"],
            elder_id=IDS["elder"],
            actor_id=IDS["worker"],
            tenant_id=IDS["tenant"],
            care_unit_id=IDS["unit"],
            relationship_type="DAYCARE_ASSIGNMENT",
            scope=SCOPES,
            effective_from=now - timedelta(minutes=1),
            effective_to=end,
        )
    )
    session.add(
        ConsentGrant(
            id=IDS["consent"],
            elder_id=IDS["elder"],
            purpose_code="CARE_EVENT_EXTRACTION",
            version=1,
            granted_by_actor_id=IDS["worker"],
            policy_id=IDS["policy"],
            scope={"synthetic": True},
            granted_at=now,
            effective_at=now - timedelta(minutes=1),
            expires_at=end,
        )
    )
    session.flush()
    session.add(
        ConversationSession(
            id=IDS["conversation"],
            elder_id=IDS["elder"],
            tenant_id=IDS["tenant"],
            initiator_actor_id=IDS["worker"],
            initiator_type="CAREGIVER",
            language_route="ZH_TW",
            state="COMPLETED",
            started_at=now - timedelta(minutes=2),
            ended_at=now - timedelta(minutes=1),
            trace_id=CAMPAIGN,
            consent_id=IDS["consent"],
            consent_version=1,
        )
    )
    session.flush()
    for key in ("legacy_unknown", "legacy_conversation"):
        session.add(
            CareEvent(
                id=IDS[key],
                elder_id=IDS["elder"],
                tenant_id=IDS["tenant"],
                source_type=None,
                source_session_id=IDS["conversation"] if key == "legacy_conversation" else None,
                event_type="ACTIVITY",
                event_time=now - timedelta(hours=1),
                status="VERIFIED",
                consent_version=1,
            )
        )
        session.flush()
        session.add(
            CareEventVersion(
                event_id=IDS[key],
                version=1,
                structured_payload={"summary": MARKER + " " + key},
                confidence=0.9,
                evidence_text_ref="[]",
                created_by_actor_id=IDS["worker"],
            )
        )
    session.flush()
    # Exclusive bootstrap. A failed commit leaves a refusal marker; never auto-reprepare.
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    with PRIVATE.open("x", encoding="utf-8") as handle:
        json.dump(
            {
                "campaign": CAMPAIGN,
                "ids": {k: str(v) for k, v in IDS.items()},
                "expires_at": end.isoformat(),
                "account": {"email": email, "password": password},
            },
            handle,
        )


def owned(session):
    tenant = session.get(Tenant, IDS["tenant"])
    actor = session.get(Actor, IDS["worker"], with_for_update=True)
    relation = session.get(CareRelationship, IDS["relationship"], with_for_update=True)
    if not (
        tenant
        and tenant.name == MARKER
        and actor
        and actor.display_name == MARKER + " worker"
        and actor.actor_type == ROLE
        and relation
        and relation.actor_id == actor.id
        and relation.tenant_id == tenant.id
        and relation.elder_id == IDS["elder"]
        and relation.care_unit_id == IDS["unit"]
        and relation.effective_to
    ):
        raise RuntimeError("Campaign ownership mismatch")
    return actor, relation


def expire(session, retire=False):
    actor, relation = owned(session)
    now = datetime.now(UTC)
    relation.effective_to = min(relation.effective_to, now)
    if not retire:
        return
    for key, unit in [("login_membership", None), ("unit_membership", IDS["unit"])]:
        row = session.get(ActorTenantMembership, IDS[key], with_for_update=True)
        if not (
            row
            and row.actor_id == actor.id
            and row.tenant_id == IDS["tenant"]
            and row.care_unit_id == unit
            and row.role_code == ROLE
            and row.effective_to
        ):
            raise RuntimeError("Membership ownership mismatch")
        row.effective_to = min(row.effective_to, now)
    actor.status = "INACTIVE"
    for model, key in [
        (PasswordCredential, "credential"),
        (ExternalIdentity, "identity"),
    ]:
        row = session.get(model, IDS[key], with_for_update=True)
        if not row or row.actor_id != actor.id:
            raise RuntimeError("Credential ownership mismatch")
        if row.status == "ACTIVE":
            row.status = "REVOKED"
            row.revoked_at = now
            row.version += 1
    for row in session.scalars(
        select(AppSession)
        .where(AppSession.actor_id == actor.id, AppSession.status == "ACTIVE")
        .with_for_update()
    ):
        row.status = "REVOKED"
        row.revoked_at = max(now, row.authenticated_at)
        row.version += 1
    grant = session.get(ConsentGrant, IDS["consent"], with_for_update=True)
    policy = session.get(PolicyRegistry, IDS["policy"], with_for_update=True)
    if not (
        grant
        and grant.elder_id == IDS["elder"]
        and grant.policy_id == IDS["policy"]
        and policy
        and policy.owner_tenant_id == IDS["tenant"]
    ):
        raise RuntimeError("Consent ownership mismatch")
    grant.expires_at = min(grant.expires_at, now)
    policy.effective_to = min(policy.effective_to, now)


def inspect(session):
    events = list(
        session.scalars(
            select(CareEvent).where(CareEvent.tenant_id == IDS["tenant"]).order_by(CareEvent.id)
        )
    )
    event_ids = [e.id for e in events]
    versions = list(
        session.scalars(
            select(CareEventVersion)
            .where(CareEventVersion.event_id.in_(event_ids))
            .order_by(CareEventVersion.event_id, CareEventVersion.version)
        )
    )
    reviews = list(
        session.scalars(
            select(ReviewDecision)
            .where(ReviewDecision.event_id.in_(event_ids))
            .order_by(ReviewDecision.review_id)
        )
    )
    outbox = list(
        session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.tenant_id == IDS["tenant"])
            .order_by(OutboxEvent.event_id)
        )
    )

    def digest(rows):
        return hashlib.sha256(
            json.dumps(
                [{c.key: getattr(r, c.key) for c in type(r).__mapper__.column_attrs} for r in rows],
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()

    memberships = list(
        session.scalars(
            select(ActorTenantMembership).where(ActorTenantMembership.actor_id == IDS["worker"])
        )
    )
    auth_sessions = list(
        session.scalars(select(AppSession).where(AppSession.actor_id == IDS["worker"]))
    )
    credential = session.get(PasswordCredential, IDS["credential"])
    relation = session.get(CareRelationship, IDS["relationship"])
    now = datetime.now(UTC)
    return {
        "campaign": CAMPAIGN,
        "revision": session.scalar(text("SELECT version_num FROM public.alembic_version")),
        "prepared": bool(session.get(Tenant, IDS["tenant"])),
        "events": [
            {
                "id": str(e.id),
                "type": e.event_type,
                "time": e.event_time,
                "status": e.status,
                "version": e.current_version,
                "source_type": e.source_type,
                "has_session": e.source_session_id is not None,
            }
            for e in events
        ],
        "versions": len(versions),
        "reviews": [
            {
                "event_id": str(r.event_id),
                "decision": r.decision,
                "before_version": r.before_version,
                "after_version": r.after_version,
                "before_type": r.before_event_type,
                "after_type": r.after_event_type,
                "before_time": r.before_event_time,
                "after_time": r.after_event_time,
            }
            for r in reviews
        ],
        "outbox": [
            {
                "type": r.event_type,
                "aggregate": str(r.aggregate_id),
                "version": r.aggregate_version,
            }
            for r in outbox
        ],
        "event_history_outbox_sha256": digest([*events, *versions, *reviews, *outbox]),
        "v1_sha256": digest([v for v in versions if v.version == 1]),
        "live_memberships": sum(r.effective_from <= now < r.effective_to for r in memberships),
        "live_relationship": bool(
            relation and relation.effective_from <= now < relation.effective_to
        ),
        "active_credential": bool(credential and credential.status == "ACTIVE"),
        "active_sessions": sum(r.status == "ACTIVE" for r in auth_sessions),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["inspect", "prepare", "expire", "retire"],
        nargs="?",
        default="inspect",
    )
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--allow-synthetic-write", action="store_true")
    args = parser.parse_args()
    if args.command != "inspect" and not args.allow_synthetic_write:
        raise RuntimeError("Explicit synthetic write opt-in required")
    settings = Settings(_env_file=args.env_file)
    validate_target(settings)
    engine = create_engine(
        to_psycopg_database_url(settings.database_url),
        hide_parameters=True,
        connect_args={
            "connect_timeout": 15,
            "options": "-c lock_timeout=5s -c statement_timeout=60s",
        },
    )
    try:
        with Session(engine, expire_on_commit=False) as session, session.begin():
            if args.command == "inspect":
                session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            if (
                session.scalar(text("SELECT version_num FROM public.alembic_version"))
                != "a5c7e9f1b324"
            ):
                raise RuntimeError("Expected B03/B04 schema required")
            if args.command == "prepare":
                prepare(session, settings)
            if args.command in {"expire", "retire"}:
                expire(session, args.command == "retire")
            session.flush()
            result = inspect(session)
        if args.command == "retire" and PRIVATE.exists():
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
        print(json.dumps(result, default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            json.dumps(
                {
                    "result": "failed",
                    "error_type": type(error).__name__,
                    "sqlstate": getattr(getattr(error, "orig", error), "sqlstate", None),
                }
            )
        )
        sys.exit(1)
