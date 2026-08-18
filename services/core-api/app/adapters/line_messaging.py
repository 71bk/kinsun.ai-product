"""Minimal LINE Messaging API client with secret-safe failures."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.core.exceptions import ServiceUnavailableError
from app.core.line_messaging import LineDailyReportNotice, LineReply

_LINE_API_BASE_URL = "https://api.line.me"
_LINE_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{1,128}$")


def _suppress_sensitive_http_client_logs() -> None:
    """Prevent HTTP client URL/header/body logs for LINE credential traffic."""
    for logger_name in ("httpx", "httpcore"):
        client_logger = logging.getLogger(logger_name)
        if client_logger.getEffectiveLevel() < logging.WARNING:
            client_logger.setLevel(logging.WARNING)


class LineMessagingClient:
    """Issue link tokens and consume one-time reply tokens without logging them."""

    def __init__(
        self,
        *,
        channel_access_token: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not channel_access_token.strip():
            raise ValueError("LINE channel access token is required")
        _suppress_sensitive_http_client_logs()
        self._channel_access_token = channel_access_token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def issue_link_token(self, line_user_id: str) -> str:
        if not _LINE_USER_ID_PATTERN.fullmatch(line_user_id):
            raise ServiceUnavailableError("LINE account linking is unavailable")
        payload = await self._post(
            f"/v2/bot/user/{line_user_id}/linkToken",
            json_body=None,
        )
        link_token = payload.get("linkToken") if isinstance(payload, dict) else None
        if not isinstance(link_token, str) or not link_token or len(link_token) > 2048:
            raise ServiceUnavailableError("LINE account linking is unavailable")
        return link_token

    async def reply(self, reply_token: str, reply: LineReply) -> None:
        if not isinstance(reply_token, str) or not reply_token:
            return
        text = reply.text.strip()
        if not text:
            raise ServiceUnavailableError("LINE reply is unavailable")
        if reply.account_link_url is None:
            messages: list[dict[str, Any]] = [{"type": "text", "text": text[:5000]}]
        else:
            if len(reply.account_link_url) > 1000:
                raise ServiceUnavailableError("LINE account linking is unavailable")
            messages = [
                {
                    "type": "template",
                    "altText": "連結 kinsun.ai 帳號",
                    "template": {
                        "type": "buttons",
                        "text": text[:160],
                        "actions": [
                            {
                                "type": "uri",
                                "label": "連結帳號",
                                "uri": reply.account_link_url,
                            }
                        ],
                    },
                }
            ]
        await self._post(
            "/v2/bot/message/reply",
            json_body={"replyToken": reply_token, "messages": messages},
        )

    async def push_daily_report(
        self,
        *,
        line_user_id: str,
        notice: LineDailyReportNotice,
        retry_key: str,
    ) -> None:
        """Push one minimal daily-report reminder with provider idempotency."""
        if not _LINE_USER_ID_PATTERN.fullmatch(line_user_id):
            raise ServiceUnavailableError("LINE push delivery is unavailable")
        if not notice.report_date or len(notice.report_date) != 10:
            raise ServiceUnavailableError("LINE push delivery is unavailable")
        if not notice.action_url.startswith("https://") or len(notice.action_url) > 1000:
            raise ServiceUnavailableError("LINE push delivery is unavailable")
        message = {
            "type": "template",
            "altText": "昨日照護摘要已更新",
            "template": {
                "type": "buttons",
                "text": f"{notice.report_date} 的照護摘要已更新。請登入後查看。",
                "actions": [
                    {
                        "type": "uri",
                        "label": "登入查看摘要",
                        "uri": notice.action_url,
                    }
                ],
            },
        }
        await self._post(
            "/v2/bot/message/push",
            json_body={"to": line_user_id, "messages": [message]},
            extra_headers={"X-Line-Retry-Key": retry_key},
        )

    async def _post(
        self,
        path: str,
        *,
        json_body: dict[str, Any] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=_LINE_API_BASE_URL,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    path,
                    headers={
                        "Authorization": f"Bearer {self._channel_access_token}",
                        **(extra_headers or {}),
                    },
                    json=json_body,
                )
                response.raise_for_status()
                if not response.content:
                    return {}
                return response.json()
        except (httpx.HTTPError, ValueError):
            raise ServiceUnavailableError("LINE Messaging API is unavailable") from None
