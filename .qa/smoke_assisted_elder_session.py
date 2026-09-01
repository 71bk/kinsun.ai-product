"""Rollback-only Supabase smoke for accountless Elder tablet handoff."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-api"))

from app.core.auth import ActorContext  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.exceptions import AuthenticationError, NotFoundError  # noqa: E402
from app.domain.conversation import (  # noqa: E402
    ConversationStartCommand,
    LanguageRoute,
)
from app.models.actor import Actor  # noqa: E402
from app.models.care_unit import CareUnit  # noqa: E402
from app.models.membership import ActorTenantMembership  # noqa: E402
from app.models.policy import PolicyRegistry  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.schemas.assisted_elder import (  # noqa: E402
    CareProfileEntryInput,
    CreateAccountlessElderRequest,
)
from app.services.assisted_elder_session_service import (  # noqa: E402
    AssistedElderSessionPolicy,
    AssistedElderSessionService,
)
from app.services.consent_service import ConsentService  # noqa: E402
from app.services.conversation_service import ConversationService  # noqa: E402
from app.services.elder_onboarding_service import ElderOnboardingService  # noqa: E402


async def run() -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        tenant_id = uuid4()
        actor_id = uuid4()
        care_unit_id = uuid4()
        effective_from = datetime.now(UTC) - timedelta(minutes=1)
        suffix = str(tenant_id)[:8]
        session.add_all(
            [
                Tenant(
                    id=tenant_id,
                    tenant_type="DEMO",
                    name=f"Synthetic assisted Elder smoke {suffix}",
                    status="ACTIVE",
                    timezone="Asia/Taipei",
                ),
                Actor(
                    id=actor_id,
                    actor_type="DAYCARE_CARE_WORKER",
                    display_name=f"Synthetic worker {suffix}",
                    status="ACTIVE",
                ),
            ]
        )
        await session.flush()
        policy = PolicyRegistry(
            id=uuid4(),
            owner_tenant_id=tenant_id,
            policy_code="SYNTHETIC_ASSISTED_TABLET_ACKNOWLEDGEMENT",
            policy_type="CONSENT",
            version=get_settings().assisted_elder_acknowledgement_policy_version,
            status="ACTIVE",
            policy_payload={"synthetic": True, "purpose": "BASIC_VOICE"},
            effective_from=effective_from,
            approved_by_actor_id=actor_id,
        )
        session.add(policy)
        await session.flush()
        session.add(
            CareUnit(
                id=care_unit_id,
                tenant_id=tenant_id,
                unit_type="DAYCARE_CENTER",
                name=f"Synthetic unit {suffix}",
                status="ACTIVE",
                timezone="Asia/Taipei",
            )
        )
        await session.flush()
        session.add_all(
            [
                ActorTenantMembership(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    care_unit_id=None,
                    role_code="DAYCARE_CARE_WORKER",
                    status="ACTIVE",
                    effective_from=effective_from,
                ),
                ActorTenantMembership(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    care_unit_id=care_unit_id,
                    role_code="DAYCARE_CARE_WORKER",
                    status="ACTIVE",
                    effective_from=effective_from,
                ),
            ]
        )
        await session.flush()

        actor_context = ActorContext(
            actor_id=actor_id,
            actor_role="DAYCARE_CARE_WORKER",
            tenant_id=tenant_id,
        )
        bundle = await ElderOnboardingService(session, tenant_id).create(
            organization_id=tenant_id,
            actor_context=actor_context,
            request=CreateAccountlessElderRequest(
                display_name="Synthetic accountless Elder",
                preferred_name="Synthetic Elder",
                preferred_language="ZH_TW",
                primary_care_setting="DAYCARE",
                care_unit_id=care_unit_id,
                response_length_preference="SHORT",
                timezone="Asia/Taipei",
                care_profile=[
                    CareProfileEntryInput(
                        category="CARE_PRECAUTION",
                        content="Synthetic provenance-only precaution",
                    )
                ],
            ),
        )
        assert bundle.elder.actor_id is None
        assert len(bundle.care_profile) == 1
        assert bundle.care_profile[0].verification_status == "RECORDED"

        assisted = AssistedElderSessionService(
            session,
            AssistedElderSessionPolicy(
                pairing_ttl=timedelta(minutes=10),
                idle_ttl=timedelta(minutes=30),
                absolute_ttl=timedelta(hours=8),
            ),
            enabled=True,
        )
        issued = await assisted.issue(
            actor_context=actor_context,
            elder_id=bundle.elder.id,
        )
        activated = await assisted.exchange(issued.pairing_token)
        resolved = await assisted.resolve_current(
            activated.session_token,
            requested_action="voice_session:read",
        )
        assert resolved.elder.id == bundle.elder.id
        assert resolved.actor_context.actor_id == actor_id

        conversation_service = ConversationService(session, tenant_id)
        missing_acknowledgement_rejected = False
        try:
            await conversation_service.create(
                elder_id=bundle.elder.id,
                actor_id=actor_id,
                actor_role=actor_context.actor_role,
                command=ConversationStartCommand(
                    language_route=LanguageRoute.ZH_TW,
                    input_mode="text",
                ),
                trace_id=f"synthetic-before-ack-{uuid4()}",
                idempotency_key=f"synthetic-before-ack-{uuid4()}",
            )
        except NotFoundError:
            missing_acknowledgement_rejected = True
        assert missing_acknowledgement_rejected

        consent_service = ConsentService(session, tenant_id)
        consent = await consent_service.acknowledge_assisted_basic_voice(
            elder_id=bundle.elder.id,
            recorded_by_actor_id=actor_id,
            assisted_session_id=resolved.assisted_session.id,
            policy_version=policy.version,
            trace_id=f"synthetic-ack-{uuid4()}",
            idempotency_key=f"synthetic-ack-{uuid4()}",
        )
        assert consent.granted_by_actor_id is None
        assert consent.recorded_by_actor_id == actor_id
        assert consent.assisted_session_id == resolved.assisted_session.id
        assert consent.confirmation_method == "ASSISTED_TABLET_ACKNOWLEDGEMENT"

        conversation = await conversation_service.create(
            elder_id=bundle.elder.id,
            actor_id=actor_id,
            actor_role=actor_context.actor_role,
            command=ConversationStartCommand(
                language_route=LanguageRoute.ZH_TW,
                input_mode="text",
            ),
            trace_id=f"synthetic-after-ack-{uuid4()}",
            idempotency_key=f"synthetic-after-ack-{uuid4()}",
        )
        assert conversation.consent_id == consent.id
        assert conversation.consent_version == consent.version
        assert conversation.policy_version == policy.version

        await consent_service.revoke_assisted_basic_voice(
            elder_id=bundle.elder.id,
            recorded_by_actor_id=actor_id,
            assisted_session_id=resolved.assisted_session.id,
            trace_id=f"synthetic-revoke-{uuid4()}",
            idempotency_key=f"synthetic-revoke-{uuid4()}",
        )
        assert conversation.state == "CANCELLED"
        revoked_acknowledgement_rejected = False
        try:
            await conversation_service.create(
                elder_id=bundle.elder.id,
                actor_id=actor_id,
                actor_role=actor_context.actor_role,
                command=ConversationStartCommand(
                    language_route=LanguageRoute.ZH_TW,
                    input_mode="text",
                ),
                trace_id=f"synthetic-after-revoke-{uuid4()}",
                idempotency_key=f"synthetic-after-revoke-{uuid4()}",
            )
        except NotFoundError:
            revoked_acknowledgement_rejected = True
        assert revoked_acknowledgement_rejected

        reused_pairing_rejected = False
        try:
            await assisted.exchange(issued.pairing_token)
        except AuthenticationError:
            reused_pairing_rejected = True
        assert reused_pairing_rejected
        await assisted.end(activated.session_token)

        print("accountless_elder_created=true")
        print("care_profile_provenance_preserved=true")
        print("pairing_single_use=true")
        print("elder_session_scope_rechecked=true")
        print("companion_blocked_before_acknowledgement=true")
        print("assisted_acknowledgement_provenance_preserved=true")
        print("companion_cancelled_on_revoke=true")
        print("companion_blocked_after_revoke=true")
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()
        print("transaction_rolled_back=true")


if __name__ == "__main__":
    asyncio.run(run())
