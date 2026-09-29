"""Real SQL/HTTP handoff lifecycle. Synthetic Actor/Speech auth and Agent only.

The caller owns the transaction; this test never commits or resets a database.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.adapters.agent_runtime import get_agent_runtime_client
from app.core.agent_runtime import AgentRunResult, AgentSafetyResult
from app.core.auth import ActorContext
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.middleware.actor_guard import require_active_actor
from app.middleware.speech_service_auth import require_speech_service
from app.models.actor import Actor
from app.models.care_unit import CareUnit
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.models.membership import ActorTenantMembership
from app.models.policy import PolicyRegistry
from app.models.tenant import Tenant


class SyntheticRuntime:
    def __init__(self):
        self.calls = []

    async def run(self, *, request_payload, correlation_id):
        self.calls.append(request_payload)
        assert request_payload["requested_outputs"] == []
        return AgentRunResult(
            schema_version="1.0.0",
            request_id=request_payload["request_id"],
            trace_id=request_payload["trace_id"],
            agent_run_id=request_payload["agent_run_id"],
            selected_agent="companion-agent",
            reply_text="很高興和您聊天。",
            reply_language="zh-TW",
            safety_result=AgentSafetyResult("1.0.0", "ALLOW", "LOW", ["ALLOW"], [], None),
            context_manifest_id="synthetic-assisted-context",
            step_count=1,
            result_status="SUCCESS",
            reason_codes=["ALLOW"],
        )


@pytest.mark.asyncio(loop_scope="function")
async def test_assisted_voice_http_lifecycle(db_session, monkeypatch):
    db = db_session
    settings = get_settings()
    policy_version = f"synthetic-voice-{uuid4().hex[:8]}"
    overrides = {
        "assisted_elder_sessions_enabled": True,
        "assisted_elder_acknowledgement_policy_version": policy_version,
        "voice_ticket_enabled": True,
        "voice_ticket_hmac_secret": "synthetic-ticket-" + "a" * 32,
        "asr_gate_enabled": True,
        "asr_gate_hmac_secret": "synthetic-asr-" + "b" * 32,
        "speech_synthesis_capability_enabled": True,
        "speech_synthesis_capability_hmac_secret": "synthetic-tts-" + "c" * 32,
        "speech_service_identity_enabled": True,
        "speech_service_identity_hmac_secret": "synthetic-speech-service-" + "d" * 32,
        "care_profile_ai_context_enabled": False,
    }
    for key, value in overrides.items():
        monkeypatch.setattr(settings, key, value)
    Settings.model_validate({name: getattr(settings, name) for name in Settings.model_fields})
    now = datetime.now(UTC)
    tenant = Tenant(id=uuid4(), name="Synthetic assisted voice", tenant_type="CARE_ORGANIZATION")
    worker = Actor(
        id=uuid4(), actor_type="DAYCARE_CARE_WORKER", display_name="Synthetic voice staff"
    )
    db.add_all([tenant, worker])
    await db.flush()
    unit = CareUnit(
        id=uuid4(), tenant_id=tenant.id, unit_type="DAYCARE_CENTER", name="Synthetic voice unit"
    )
    db.add(unit)
    await db.flush()
    for care_unit_id in [None, unit.id]:
        db.add(
            ActorTenantMembership(
                actor_id=worker.id,
                tenant_id=tenant.id,
                care_unit_id=care_unit_id,
                role_code="DAYCARE_CARE_WORKER",
                status="ACTIVE",
                effective_from=now - timedelta(minutes=1),
                effective_to=now + timedelta(hours=1),
            )
        )
    db.add(
        PolicyRegistry(
            owner_tenant_id=tenant.id,
            policy_code=f"synthetic-{uuid4().hex}",
            policy_type="CONSENT",
            version=policy_version,
            status="ACTIVE",
            policy_payload={},
            effective_from=now - timedelta(minutes=1),
        )
    )
    await db.flush()
    actor = ActorContext(actor_id=worker.id, actor_role=worker.actor_type, tenant_id=tenant.id)
    runtime = SyntheticRuntime()
    app = create_app()

    async def request_session():
        async with db.begin_nested():
            yield db

    app.dependency_overrides[get_db_session] = request_session
    app.dependency_overrides[require_active_actor] = lambda: actor
    app.dependency_overrides[require_speech_service] = lambda: None
    app.dependency_overrides[get_agent_runtime_client] = lambda: runtime
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def post(path, body=None, token=None, expected=200):
            headers = {"Idempotency-Key": str(uuid4())}
            if token:
                headers["Authorization"] = "Bearer " + token
            response = await client.post(path, json=body or {}, headers=headers)
            assert response.status_code == expected, f"{path}: {response.status_code}"
            return response.json()["data"] if expected < 300 else response

        elder = await post(
            f"/api/v1/organizations/{tenant.id}/elders",
            {
                "display_name": "Synthetic accountless elder",
                "care_unit_id": str(unit.id),
            },
            expected=201,
        )
        elder_id = UUID(elder["elder_id"])
        assert (await db.get(Elder, elder_id)).actor_id is None
        issued = await post(f"/api/v1/elders/{elder_id}/assisted-sessions", expected=201)
        ack_path = (
            f"/api/v1/elders/{elder_id}/assisted-sessions/"
            f"{issued['assisted_session_id']}/acknowledgement"
        )
        await post(ack_path, {"explanation_given": True, "elder_agreed": False}, expected=422)
        ack = await post(ack_path, {"explanation_given": True, "elder_agreed": True})
        assert ack["status"] == "ACKNOWLEDGED"
        consent = await db.scalar(select(ConsentGrant).where(ConsentGrant.elder_id == elder_id))
        assert consent.granted_by_actor_id is None and consent.recorded_by_actor_id == worker.id
        assert consent.scope["assistance_method"] == "STAFF_RECORDED_VERBAL"
        activated = await post(
            "/api/v1/assisted-elder-sessions/exchange", {"pairing_token": issued["pairing_token"]}
        )
        token = activated["session_token"]
        await post(
            "/api/v1/assisted-elder-sessions/exchange",
            {"pairing_token": issued["pairing_token"]},
            expected=401,
        )
        base = "/api/v1/assisted-elder-sessions/current"

        async def voice(confidence):
            ticket = await post(
                base + "/voice-tickets", {"language_preference": "ZH_TW"}, token, 201
            )
            sid = ticket["voice_session"]["session_id"]
            conversation = await db.get(ConversationSession, UUID(sid))
            assert str(conversation.assisted_session_id) == issued["assisted_session_id"]
            await post(
                "/api/v1/internal/voice-tickets/consume",
                {"session_id": sid, "voice_ticket": ticket["voice_ticket"]},
            )
            gate = await post(
                "/api/v1/internal/asr-results",
                {
                    "session_id": sid,
                    "language_route": "ZH_TW",
                    "asr_model_version": "synthetic-assist-v1",
                    "confidence": confidence,
                    "transcript": "今天想聊聊天",
                },
            )
            return sid, gate

        low, gate = await voice(0.1)
        assert gate["decision"] == "CONFIRMATION_REQUIRED"
        await post(
            f"{base}/voice-sessions/{low}/companion-turns",
            {"input_text": "今天想聊聊天"},
            token,
            409,
        )
        assert not runtime.calls
        await post(f"{base}/voice-sessions/{low}/cancel", token=token)
        sid, gate = await voice(0.99)
        assert gate["decision"] == "CAN_SEND_TO_AGENT"
        result = await post(
            f"{base}/voice-sessions/{sid}/companion-turns", {"input_text": "今天想聊聊天"}, token
        )
        assert result["transport_status"] == "SYNTHESIS_CAPABILITY_ISSUED"
        assert result["memory_updates"] == [] and len(runtime.calls) == 1
        # A new handoff revokes the old tablet, including a ticket already issued to Speech.
        pending = await post(base + "/voice-tickets", {"language_preference": "ZH_TW"}, token, 201)
        second = await post(f"/api/v1/elders/{elder_id}/assisted-sessions", expected=201)
        await post(
            "/api/v1/internal/voice-tickets/consume",
            {
                "session_id": pending["voice_session"]["session_id"],
                "voice_ticket": pending["voice_ticket"],
            },
            expected=401,
        )
        await post(base + "/voice-tickets", {"language_preference": "ZH_TW"}, token, 401)
        new = await post(
            "/api/v1/assisted-elder-sessions/exchange", {"pairing_token": second["pairing_token"]}
        )
        await post(
            f"{base}/voice-sessions/{sid}/companion-turns",
            {"input_text": "今天想聊聊天"},
            new["session_token"],
            404,
        )
        await post(base + "/first-use-acknowledgement/revoke", token=new["session_token"])
        await post(
            base + "/voice-tickets", {"language_preference": "ZH_TW"}, new["session_token"], 404
        )
        await post(base + "/end", token=new["session_token"])
