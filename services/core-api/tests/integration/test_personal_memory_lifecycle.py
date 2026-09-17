"""Real SQL self-stated lifecycle; no graph projection or event-review fixture."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.auth import ActorContext
from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.actor import Actor
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.models.graph_projection import GraphProjectionRecord
from app.models.memory import Memory, MemoryVersion
from app.models.policy import PolicyRegistry
from app.models.tenant import Tenant
from app.services.memory_service import MemoryService
from app.services.personal_memory_service import PersonalMemoryService


@pytest.mark.asyncio
async def test_personal_lifecycle_real_sql(db_session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "personal_memory_enabled", True)
    monkeypatch.setattr(settings, "evidence_aware_memory", True)
    monkeypatch.setattr(settings, "auto_low_risk_memory", False)
    s = db_session
    tenant, actor_id, elder_id, policy_id = [uuid4() for _ in range(4)]
    now = datetime.now(UTC) - timedelta(minutes=1)
    s.add_all(
        [
            Tenant(id=tenant, tenant_type="DEMO", name="Synthetic personal memory"),
            Actor(id=actor_id, actor_type="ELDER", display_name="Synthetic personal elder"),
            PolicyRegistry(
                id=policy_id,
                policy_code=f"synthetic-{policy_id}",
                policy_type="CONSENT",
                version="v1",
                status="ACTIVE",
                policy_payload={},
            ),
        ]
    )
    await s.flush()
    s.add(
        Elder(
            id=elder_id,
            tenant_id=tenant,
            actor_id=actor_id,
            display_name="Synthetic personal elder",
            primary_care_setting="HOME_CARE",
        )
    )
    await s.flush()
    grants = {}
    for purpose in ["BASIC_VOICE", "LONG_TERM_MEMORY"]:
        grant = ConsentGrant(
            elder_id=elder_id,
            purpose_code=purpose,
            status="GRANTED",
            version=1,
            scope={"personal_memory_auto_save": True} if purpose == "LONG_TERM_MEMORY" else {},
            granted_by_actor_id=actor_id,
            confirmation_method="ACTOR_CONFIRMATION",
            recorded_by_actor_id=actor_id,
            policy_id=policy_id,
            granted_at=now,
            effective_at=now,
        )
        s.add(grant)
        grants[purpose] = grant
    await s.flush()
    actor = ActorContext(actor_id=actor_id, actor_role="ELDER", tenant_id=tenant)
    conversation = ConversationSession(
        tenant_id=tenant,
        elder_id=elder_id,
        initiator_actor_id=actor_id,
        initiator_type="ELDER",
        language_route="ZH_TW",
        input_mode="text",
        state="COMPLETED",
        trace_id=f"synthetic-{uuid4()}",
        consent_id=grants["BASIC_VOICE"].id,
        consent_version=1,
        policy_version="v1",
    )
    s.add(conversation)
    await s.flush()
    personal = PersonalMemoryService(s, tenant)
    memories = MemoryService(s, tenant)

    async def capture(content):
        return await personal.capture(
            conversation=conversation,
            actor=actor,
            text=content,
            turn_id=uuid4(),
            trace_id="synthetic-personal",
        )

    assert await capture("我爸爸每天早餐喝豆漿") == []
    saved = (await capture("我每天早餐喝豆漿"))[0]
    repeated = (await capture("我每天早餐喝豆漿"))[0]
    assert repeated == saved
    assert (
        await s.scalar(select(func.count()).select_from(Memory).where(Memory.elder_id == elder_id))
        == 1
    )
    assert (
        await s.scalar(
            select(func.count())
            .select_from(GraphProjectionRecord)
            .where(GraphProjectionRecord.source_id == saved.memory_id)
        )
        == 0
    )
    context = await memories.list_trusted_context(elder_id=elder_id, limit=8)
    assert [(r.content, r.self_stated) for r in context] == [("我每天早餐喝豆漿。", True)]
    assert (
        await MemoryService(s, uuid4()).list_for_elder(
            elder_id=elder_id, statuses=["ACTIVE"], limit=8, cursor=None
        )
        == []
    )
    memory = await memories.get(elder_id, saved.memory_id)
    # The original speaker/session must remain bound, even with a valid digest.
    conversation.input_mode = "voice"
    await s.flush()
    assert await memories.list_trusted_context(elder_id=elder_id, limit=8) == []
    conversation.input_mode = "text"
    grant = grants["LONG_TERM_MEMORY"]
    grant.scope = {}
    await s.flush()
    assert await capture("我喜歡聽老歌") == []
    assert await memories.list_trusted_context(elder_id=elder_id, limit=8) == []
    grant.scope = {"personal_memory_auto_save": True}
    await s.flush()
    await personal.edit(
        memory=memory,
        actor=actor,
        content="我每天早餐喝牛奶",
        expected_version=1,
        trace_id="synthetic-edit",
        idempotency_key="synthetic-edit",
    )
    assert memory.current_version == 2
    assert (await memories.list_trusted_context(elder_id=elder_id, limit=8))[
        0
    ].content == "我每天早餐喝牛奶。"
    with pytest.raises(ConflictError):
        await memories.delete(
            memory=memory,
            actor_id=actor_id,
            expected_version=1,
            trace_id="synthetic-delete",
            idempotency_key="stale-delete",
        )
    await memories.delete(
        memory=memory,
        actor_id=actor_id,
        expected_version=2,
        trace_id="synthetic-delete",
        idempotency_key="current-delete",
    )
    assert await memories.list_trusted_context(elder_id=elder_id, limit=8) == []
    assert (
        await s.scalars(select(MemoryVersion).where(MemoryVersion.memory_id == memory.id))
    ).all()
    await capture("我喜歡喝豆漿")  # Exercises the additive FOOD_PREFERENCE constraint.
    grant.status = "REVOKED"
    grant.revoked_at = datetime.now(UTC)
    await s.flush()
    assert await capture("我喜歡聽老歌") == []
    with pytest.raises(NotFoundError):
        await memories.list_trusted_context(elder_id=elder_id, limit=8)
