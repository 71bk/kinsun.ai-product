from __future__ import annotations

import json
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from app.adapters.line_messaging import LineDailyReportNotice, LineMessagingClient
from app.core.exceptions import ServiceUnavailableError
from app.repositories.notification_repo import DailyLineCandidate, DeliveryClaim
from app.schemas.notification import DailyLineNotificationJobRequest
from app.services.daily_line_notification_service import DailyLineNotificationService
from app.services.line_subject_cipher import LineSubjectCipher

REPORT_ID = UUID("2a6f9c31-8e47-4b52-9d10-3c8a7e5b1a40")
VERSION_ID = UUID("3a6f9c31-8e47-4b52-9d10-3c8a7e5b1a41")
ACTOR_ID = UUID("4a6f9c31-8e47-4b52-9d10-3c8a7e5b1a42")
PREFERENCE_ID = UUID("5a6f9c31-8e47-4b52-9d10-3c8a7e5b1a43")
TENANT_ID = UUID("6a6f9c31-8e47-4b52-9d10-3c8a7e5b1a44")
NOTIFICATION_ID = UUID("7a6f9c31-8e47-4b52-9d10-3c8a7e5b1a45")


class _Session:
    async def commit(self) -> None:
        return None


class _SessionContext:
    async def __aenter__(self) -> _Session:
        return _Session()

    async def __aexit__(self, *args) -> None:
        return None


class _SessionFactory:
    def __call__(self) -> _SessionContext:
        return _SessionContext()


class _Engine:
    session_factory = _SessionFactory()


class _FakeRepository:
    candidates: list[DailyLineCandidate] = []
    claim = DeliveryClaim(NOTIFICATION_ID, "CLAIMED")
    sent: list[UUID] = []
    failed: list[tuple[UUID, str, bool]] = []

    def __init__(self, session, tenant_id: UUID) -> None:
        assert tenant_id == TENANT_ID

    async def list_daily_line_candidates(self, **kwargs) -> list[DailyLineCandidate]:
        return list(self.candidates)

    async def claim_delivery(self, **kwargs) -> DeliveryClaim:
        return self.claim

    async def mark_sent(self, notification_id: UUID, **kwargs) -> None:
        self.sent.append(notification_id)

    async def mark_failed(
        self,
        notification_id: UUID,
        *,
        reason_code: str,
        terminal: bool = False,
    ) -> None:
        self.failed.append((notification_id, reason_code, terminal))


class _LineClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    async def push_daily_report(self, **kwargs) -> None:
        self.calls.append(kwargs)
        if self.fail:
            raise ServiceUnavailableError("synthetic provider failure")


@pytest.fixture(autouse=True)
def _reset_fake_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeRepository.candidates = []
    _FakeRepository.claim = DeliveryClaim(NOTIFICATION_ID, "CLAIMED")
    _FakeRepository.sent = []
    _FakeRepository.failed = []
    monkeypatch.setattr(
        "app.services.daily_line_notification_service.NotificationRepository",
        _FakeRepository,
    )


def _request(value: str = "2026-08-02T08:00:00+08:00") -> DailyLineNotificationJobRequest:
    return DailyLineNotificationJobRequest(
        schema_version="1.0",
        job_name="line-daily-family-report",
        scheduled_for=value,
        timezone="Asia/Taipei",
    )


def _candidate(cipher: LineSubjectCipher) -> DailyLineCandidate:
    return DailyLineCandidate(
        report_id=REPORT_ID,
        report_version_id=VERSION_ID,
        report_version=1,
        recipient_actor_id=ACTOR_ID,
        preference_id=PREFERENCE_ID,
        encrypted_subject=cipher.encrypt("U0123456789abcdef0123456789abcdef"),
    )


@pytest.mark.asyncio
async def test_daily_job_uses_previous_taipei_day_and_minimal_notice() -> None:
    cipher = LineSubjectCipher("synthetic-line-encryption-secret-at-least-32-bytes")
    _FakeRepository.candidates = [_candidate(cipher)]
    line_client = _LineClient()
    service = DailyLineNotificationService(
        _Engine(),
        tenant_id=TENANT_ID,
        line_client=line_client,
        subject_cipher=cipher,
        family_report_url="https://staging.example.com",
    )

    result = await service.run(_request())

    assert result.status == "COMPLETED"
    assert result.source_period.start == "2026-08-01"
    assert result.counts.sent == 1
    assert result.counts.failed == 0
    assert _FakeRepository.sent == [NOTIFICATION_ID]
    assert line_client.calls[0]["line_user_id"].startswith("U")
    notice = line_client.calls[0]["notice"]
    assert notice == LineDailyReportNotice(
        report_date="2026-08-01",
        action_url="https://staging.example.com/family/reports",
    )
    assert line_client.calls[0]["retry_key"] == str(NOTIFICATION_ID)


@pytest.mark.asyncio
async def test_provider_failure_is_recorded_without_changing_report() -> None:
    cipher = LineSubjectCipher("synthetic-line-encryption-secret-at-least-32-bytes")
    _FakeRepository.candidates = [_candidate(cipher)]
    service = DailyLineNotificationService(
        _Engine(),
        tenant_id=TENANT_ID,
        line_client=_LineClient(fail=True),
        subject_cipher=cipher,
        family_report_url="https://staging.example.com",
    )

    result = await service.run(_request())

    assert result.status == "PARTIAL_FAILURE"
    assert result.counts.failed == 1
    assert result.deliveries[0].reason_code == "LINE_PROVIDER_UNAVAILABLE"
    assert _FakeRepository.failed == [(NOTIFICATION_ID, "LINE_PROVIDER_UNAVAILABLE", False)]


@pytest.mark.asyncio
async def test_replayed_claim_does_not_call_line_again() -> None:
    cipher = LineSubjectCipher("synthetic-line-encryption-secret-at-least-32-bytes")
    _FakeRepository.candidates = [_candidate(cipher)]
    _FakeRepository.claim = DeliveryClaim(NOTIFICATION_ID, "REPLAYED", "ALREADY_SENT")
    line_client = _LineClient()
    service = DailyLineNotificationService(
        _Engine(),
        tenant_id=TENANT_ID,
        line_client=line_client,
        subject_cipher=cipher,
        family_report_url="https://staging.example.com",
    )

    result = await service.run(_request())

    assert result.counts.replayed == 1
    assert result.counts.sent == 0
    assert line_client.calls == []


def test_schedule_input_requires_exact_0800_taipei_and_forbids_extra_fields() -> None:
    assert _request("2026-08-02T00:00:00Z").scheduled_for.tzinfo is not None
    with pytest.raises(ValidationError, match="08:00:00"):
        _request("2026-08-02T08:01:00+08:00")
    with pytest.raises(ValidationError, match="Extra inputs"):
        DailyLineNotificationJobRequest.model_validate(
            {
                **_request().model_dump(mode="json"),
                "line_user_id": "U0123456789abcdef0123456789abcdef",
            }
        )


@pytest.mark.asyncio
async def test_line_push_payload_has_no_report_content_or_elder_name() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["retry_key"] = request.headers.get("X-Line-Retry-Key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    client = LineMessagingClient(
        channel_access_token="synthetic-access-token",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    await client.push_daily_report(
        line_user_id="U0123456789abcdef0123456789abcdef",
        notice=LineDailyReportNotice(
            report_date="2026-08-01",
            action_url="https://staging.example.com/family/reports",
        ),
        retry_key=str(NOTIFICATION_ID),
    )

    serialized = json.dumps(captured["body"], ensure_ascii=False)
    assert captured["path"] == "/v2/bot/message/push"
    assert captured["retry_key"] == str(NOTIFICATION_ID)
    assert "昨日照護摘要已更新" in serialized
    assert "林阿嬤" not in serialized
    assert "report_content" not in serialized
    assert "synthetic-access-token" not in serialized
