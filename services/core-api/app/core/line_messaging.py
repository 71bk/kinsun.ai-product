"""Application-facing boundary for LINE Messaging delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LineReply:
    """One reply without retaining the LINE reply token."""

    text: str
    account_link_url: str | None = None


@dataclass(frozen=True)
class LineDailyReportNotice:
    """Minimal lock-screen-safe notification; report content stays in Family Web."""

    report_date: str
    action_url: str


class LineMessagingPort(Protocol):
    """Port used by Core services for the bounded LINE operations they require."""

    async def issue_link_token(self, line_user_id: str) -> str:
        """Issue a short-lived LINE account-link token."""
        ...

    async def reply(self, reply_token: str, reply: LineReply) -> None:
        """Consume one reply token without retaining it."""
        ...

    async def push_daily_report(
        self,
        *,
        line_user_id: str,
        notice: LineDailyReportNotice,
        retry_key: str,
    ) -> None:
        """Push one minimal report notice using provider idempotency."""
        ...
