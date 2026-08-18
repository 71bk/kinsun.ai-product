"""Signed LINE webhook with account linking, deduplication, and Companion replies."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.adapters.agent_runtime import get_agent_runtime_client
from app.bootstrap.dependencies import (
    get_line_identity_codec,
    get_line_messaging_client,
    get_line_subject_cipher,
)
from app.core.agent_runtime import AgentRuntimePort
from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, DomainException, ServiceUnavailableError
from app.core.line_messaging import LineMessagingPort, LineReply
from app.db.engine import DatabaseEngine
from app.db.session import get_db_engine
from app.repositories.line_identity_repo import LineIdentityRepository
from app.services.line_account_link_service import LineAccountLinkService
from app.services.line_bot_service import LineBotService
from app.services.line_identity_codec import LineIdentityCodec

router = APIRouter(prefix="/api/v1/webhooks", tags=["line"])
logger = logging.getLogger(__name__)
_MAX_CONCURRENT_EVENTS = 4


def _is_valid_signature(
    body: bytes,
    signature: str | None,
    channel_secret: str,
) -> bool:
    """Verify the signature against the unmodified request body."""
    if not signature or not channel_secret:
        return False
    digest = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _event_operation_key(webhook_event_id: str) -> str:
    return f"line-{hashlib.sha256(webhook_event_id.encode('utf-8')).hexdigest()}"


def _fallback_reply(error: DomainException) -> LineReply:
    if isinstance(error, ConflictError):
        return LineReply("目前無法使用陪伴服務，請確認同意設定後再試。")
    return LineReply("目前無法處理這個請求，請稍後再試。")


def _is_supported_event(event: dict[str, Any]) -> bool:
    event_type = event.get("type")
    message = event.get("message")
    return event_type == "accountLink" or (
        event_type == "message" and isinstance(message, dict) and message.get("type") == "text"
    )


async def _reply_legacy_connectivity(
    events: list[dict[str, Any]],
    line_client: LineMessagingPort,
) -> None:
    for event in events:
        if event.get("type") != "message":
            continue
        message = event.get("message")
        reply_token = event.get("replyToken")
        if (
            isinstance(message, dict)
            and message.get("type") == "text"
            and isinstance(reply_token, str)
            and reply_token
        ):
            await line_client.reply(
                reply_token,
                LineReply("LINE Bot 已成功連接 kinsun.ai！"),
            )


async def _process_event(
    *,
    event: dict[str, Any],
    settings: Settings,
    db_engine: DatabaseEngine,
    line_client: LineMessagingPort,
    codec: LineIdentityCodec,
    runtime_client: AgentRuntimePort,
) -> bool:
    """Process one event in its own transaction scope; return whether LINE should retry."""
    event_type = event.get("type")
    webhook_event_id = event.get("webhookEventId")
    if not isinstance(webhook_event_id, str) or not webhook_event_id or len(webhook_event_id) > 128:
        return False

    reply_token = event.get("replyToken")
    reply: LineReply | None = None
    async with db_engine.session_factory() as session:
        account_links = LineAccountLinkService(
            session,
            codec,
            challenge_ttl_seconds=settings.line_link_challenge_ttl_seconds,
            challenge_max_attempts=settings.line_link_challenge_max_attempts,
            frontend_base_url=settings.line_account_link_base_url,
            subject_cipher=(
                get_line_subject_cipher() if settings.line_daily_notification_enabled else None
            ),
        )
        bot = LineBotService(
            session,
            account_links=account_links,
            line_client=line_client,
            runtime_client=runtime_client,
            model_route=settings.agent_runtime_model_id,
            runtime_timeout_seconds=settings.agent_runtime_timeout_seconds,
        )
        receipts = LineIdentityRepository(session)
        claim_result = await receipts.claim_webhook_event(
            webhook_event_id=webhook_event_id,
            event_type=str(event_type),
        )
        # Persist the claim independently. A crash after this point is recovered
        # by stale PROCESSING reclamation without retaining any reply token.
        await session.commit()
        if claim_result == "RETRY_LATER":
            return True
        if claim_result != "CLAIMED":
            return False

        try:
            source = event.get("source")
            line_user_id = source.get("userId") if isinstance(source, dict) else None
            if event_type == "accountLink":
                link = event.get("link")
                nonce = link.get("nonce") if isinstance(link, dict) else None
                link_result = link.get("result") if isinstance(link, dict) else None
                if not isinstance(nonce, str) or not isinstance(link_result, str):
                    reply = LineReply("帳號連結失敗，請重新輸入「連結帳號」。")
                else:
                    linked = await account_links.redeem_account_link(
                        nonce=nonce,
                        line_user_id=line_user_id if isinstance(line_user_id, str) else "",
                        result=link_result,
                        trace_id=_event_operation_key(webhook_event_id),
                        idempotency_key=_event_operation_key(webhook_event_id),
                    )
                    reply = LineReply(
                        "帳號連結成功。你可以在 kinsun.ai 網站隨時解除連結。"
                        if linked
                        else "帳號連結失敗或已失效，請重新輸入「連結帳號」。"
                    )
            else:
                message = event.get("message")
                if isinstance(line_user_id, str) and isinstance(message, dict):
                    message_text = message.get("text")
                    if isinstance(message_text, str):
                        reply = await bot.handle_text_message(
                            line_user_id=line_user_id,
                            message_text=message_text,
                            webhook_event_id=webhook_event_id,
                        )
        except ServiceUnavailableError as exc:
            await session.rollback()
            await receipts.fail_webhook_event(
                webhook_event_id,
                error_code=type(exc).__name__,
            )
            await session.commit()
            logger.warning(
                "line_webhook_event_retryable_failure",
                extra={"event_type": str(event_type)},
            )
            return True
        except DomainException as exc:
            # Deterministic policy/validation failures must not retain partial
            # domain work and are safe to mark terminal with a bounded reply.
            await session.rollback()
            reply = _fallback_reply(exc)
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            await receipts.fail_webhook_event(
                webhook_event_id,
                error_code=type(exc).__name__,
            )
            await session.commit()
            logger.error(
                "line_webhook_event_retryable_failure",
                extra={"event_type": str(event_type)},
            )
            return True

        await receipts.complete_webhook_event(webhook_event_id)
        # Commit this event's receipt and domain state before consuming its
        # one-time reply token. Reply loss after commit is an explicit MVP
        # at-most-once tradeoff; tokens are never persisted for recovery.
        await session.commit()

    if isinstance(reply_token, str) and reply_token and reply is not None:
        try:
            await line_client.reply(reply_token, reply)
        except ServiceUnavailableError:
            logger.warning("line_reply_delivery_failed")
    return False


@router.post("/line", status_code=status.HTTP_200_OK)
async def receive_line_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db_engine: Annotated[DatabaseEngine, Depends(get_db_engine)],
    x_line_signature: Annotated[
        str | None,
        Header(alias="X-Line-Signature"),
    ] = None,
) -> dict[str, bool]:
    """Validate the signature, dedupe domain work, and reply at most once."""
    if not settings.line_channel_secret or not settings.line_channel_access_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LINE Messaging API is not configured",
        )

    raw_body = await request.body()
    if not _is_valid_signature(raw_body, x_line_signature, settings.line_channel_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid LINE signature",
        )
    try:
        payload: Any = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        )

    events = payload["events"]
    if any(not isinstance(event, dict) for event in events):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook event",
        )
    typed_events: list[dict[str, Any]] = events
    line_client = get_line_messaging_client()
    if not settings.line_account_link_enabled:
        await _reply_legacy_connectivity(typed_events, line_client)
        return {"ok": True}
    if not db_engine.is_ready:
        raise ServiceUnavailableError("Database is unavailable")

    codec = get_line_identity_codec()
    runtime_client = get_agent_runtime_client()
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_EVENTS)

    async def process_bounded(event: dict[str, Any]) -> bool:
        async with semaphore:
            return await _process_event(
                event=event,
                settings=settings,
                db_engine=db_engine,
                line_client=line_client,
                codec=codec,
                runtime_client=runtime_client,
            )

    supported_events = [event for event in typed_events if _is_supported_event(event)]
    results = await asyncio.gather(
        *(process_bounded(event) for event in supported_events),
        return_exceptions=True,
    )
    if any(isinstance(result, BaseException) for result in results):
        raise ServiceUnavailableError("LINE webhook processing is unavailable")
    if any(result is True for result in results):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="One or more LINE events require retry",
        )
    return {"ok": True}
