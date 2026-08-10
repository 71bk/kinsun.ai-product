"""Synchronous LINE message orchestration through Core authorization gates."""

from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.agent_runtime import AgentRuntimeClient
from app.adapters.line_messaging import LineMessagingClient, LineReply
from app.schemas.conversation import CreateVoiceSessionRequest, LanguageRoute
from app.services.authorization_service import authorize_elder
from app.services.companion_service import CompanionService
from app.services.conversation_service import ConversationService
from app.services.line_account_link_service import LineAccountLinkService

_LINK_COMMANDS = {"連結帳號", "綁定帳號"}


class LineBotService:
    """Handle one text event without persisting its plaintext."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        account_links: LineAccountLinkService,
        line_client: LineMessagingClient,
        runtime_client: AgentRuntimeClient,
        model_route: str,
        runtime_timeout_seconds: float,
    ) -> None:
        self._session = session
        self._account_links = account_links
        self._line_client = line_client
        self._runtime_client = runtime_client
        self._model_route = model_route
        self._runtime_timeout_seconds = runtime_timeout_seconds

    async def handle_text_message(
        self,
        *,
        line_user_id: str,
        message_text: str,
        webhook_event_id: str,
    ) -> LineReply:
        normalized = message_text.strip()
        if normalized in _LINK_COMMANDS:
            linked_actor_type = await self._account_links.resolve_linked_actor_type(line_user_id)
            if linked_actor_type is not None:
                return LineReply("此 LINE 帳號已連結。你可以在 kinsun.ai 網站隨時解除連結。")
            link_token = await self._line_client.issue_link_token(line_user_id)
            return LineReply(
                "請登入 kinsun.ai 完成帳號連結；完成後可隨時在網站解除連結。",
                account_link_url=self._account_links.build_frontend_start_url(link_token),
            )

        if not normalized:
            return LineReply("請輸入訊息，或輸入「連結帳號」開始連結。")
        if len(message_text) > 4000:
            return LineReply("訊息內容過長，請縮短後再試。")

        resolved = await self._account_links.resolve_line_actor(line_user_id)
        if resolved is None:
            if await self._account_links.resolve_linked_actor_type(line_user_id) == "FAMILY_MEMBER":
                return LineReply("此帳號用於接收家屬通知；詳細內容請從通知中的安全連結開啟。")
            return LineReply("請先輸入「連結帳號」完成帳號連結。")

        actor = resolved.actor_context
        elder = resolved.elder
        await authorize_elder(
            self._session,
            actor,
            elder.id,
            "voice_session:create",
        )
        operation_key = self._operation_key(webhook_event_id)
        conversation = await ConversationService(self._session, actor.tenant_id).create(
            elder_id=elder.id,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            request=CreateVoiceSessionRequest(
                language_preference=LanguageRoute(elder.preferred_language),
                input_mode="text",
                client_timezone=elder.timezone,
            ),
            trace_id=operation_key,
            idempotency_key=operation_key,
        )
        await authorize_elder(
            self._session,
            actor,
            elder.id,
            "voice_session:control",
        )
        response = await CompanionService(
            self._session,
            actor.tenant_id,
            self._runtime_client,
            self._model_route,
        ).run_turn(
            conversation=conversation,
            actor_context=actor,
            input_text=message_text,
            correlation_id=operation_key,
            idempotency_key=operation_key,
            latency_budget_ms=min(
                300_000,
                max(100, round(self._runtime_timeout_seconds * 1000)),
            ),
        )
        return LineReply(response.reply_text)

    @staticmethod
    def _operation_key(webhook_event_id: str) -> str:
        digest = hashlib.sha256(webhook_event_id.encode("utf-8")).hexdigest()
        return f"line-{digest}"
