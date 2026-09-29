"""Live authorization for conversations created by a tablet handoff."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.domain.consent import ConsentPurpose
from app.models.conversation import ConversationSession
from app.services.assisted_elder_session_service import (
    AssistedElderSessionPolicy,
    AssistedElderSessionService,
)
from app.services.consent_service import ConsentService


async def require_live_assisted_conversation(
    session: AsyncSession,
    conversation: ConversationSession,
) -> None:
    if getattr(conversation, "assisted_session_id", None) is None:
        return
    settings = get_settings()
    await AssistedElderSessionService(
        session,
        AssistedElderSessionPolicy.from_settings(settings),
        enabled=settings.assisted_elder_sessions_enabled,
    ).require_bound_conversation(conversation)
    consent = await ConsentService(session, conversation.tenant_id).require_active(
        elder_id=conversation.elder_id,
        purpose=ConsentPurpose.BASIC_VOICE,
    )
    if consent.id != conversation.consent_id or consent.version != conversation.consent_version:
        raise AuthenticationError("Assisted Elder Session is unavailable")
