"""Actor-owned opt-in, fail-closed readiness, safe output and stale-write tests."""

from datetime import UTC, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.auth import ActorContext
from app.core.exceptions import ConflictError, NotFoundError
from app.schemas.family_notification_preference import UpdateFamilyLineNotificationPreference
from app.services.family_notification_preference_service import FamilyNotificationPreferenceService
from app.services.line_subject_cipher import LineSubjectCipher

NOW = datetime.now(UTC)


def preference(**overrides):
    return SimpleNamespace(
        **{
            "id": uuid4(),
            "channels": ["EMAIL", "LINE"],
            "frequency": "DAILY",
            "timezone": "Asia/Taipei",
            "send_time_local": time(8),
            "quiet_hours": {},
            "status": "ACTIVE",
            "version": 2,
            "updated_at": NOW,
            "important_event_enabled": True,
            **overrides,
        }
    )


def service(*, available=True, identity=None, cipher=None, role="FAMILY_MEMBER"):
    session = MagicMock()
    session.scalar = AsyncMock(return_value=identity)
    session.flush = AsyncMock()
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role=role)
    settings = SimpleNamespace(
        line_daily_notification_enabled=available, line_account_link_enabled=available
    )
    return FamilyNotificationPreferenceService(session, actor, settings, subject_cipher=cipher)


@pytest.mark.parametrize(
    "body",
    [
        {"line_enabled": "true", "expected_version": 0},
        {"line_enabled": True, "expected_version": True},
        {"line_enabled": False, "expected_version": -1},
        {"line_enabled": False, "expected_version": 0, "family_actor_id": str(uuid4())},
        {"line_enabled": False, "expected_version": 0, "channels": ["LINE"]},
    ],
)
def test_rejects_coercion_or_recipient_override(body):
    with pytest.raises(ValidationError):
        UpdateFamilyLineNotificationPreference.model_validate(body)


@pytest.mark.asyncio
async def test_no_row_is_default_off_without_creating_preference():
    sut = service(available=False)
    result = await sut._response(uuid4(), None)
    assert result.version == 0 and not result.line_enabled and result.preference_id is None
    assert result.availability == "SERVICE_UNAVAILABLE"
    sut._session.add.assert_not_called()
    assert set(result.model_dump()) == {
        "schema_version",
        "elder_id",
        "preference_id",
        "line_enabled",
        "version",
        "frequency",
        "send_time_local",
        "timezone",
        "line_status",
        "availability",
        "line_link_available",
        "can_enable",
        "updated_at",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "encrypted,expected", [(None, "RELINK_REQUIRED"), ("bad", "RELINK_REQUIRED")]
)
async def test_oidc_only_or_bad_encryption_cannot_enable(encrypted, expected):
    cipher = LineSubjectCipher("synthetic-line-secret-material-at-least-32-bytes")
    sut = service(identity=SimpleNamespace(encrypted_external_subject=encrypted), cipher=cipher)
    result = await sut._response(uuid4(), None)
    assert result.line_status == expected and not result.can_enable
    assert result.availability == "LINE_LINK_REQUIRED"
    assert "encrypted" not in repr(result.model_dump())


@pytest.mark.asyncio
async def test_valid_destination_is_ready_without_provider_call():
    cipher = LineSubjectCipher("synthetic-line-secret-material-at-least-32-bytes")
    sut = service(
        identity=SimpleNamespace(encrypted_external_subject=cipher.encrypt("Usynthetic123")),
        cipher=cipher,
    )
    result = await sut._response(uuid4(), None)
    assert result.can_enable and result.line_status == "LINKED"
    assert "Usynthetic123" not in repr(result.model_dump())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"frequency": "WEEKLY"},
        {"timezone": "UTC"},
        {"send_time_local": time(9)},
        {"send_time_local": None},
        {"quiet_hours": {"start": "07:00"}},
        {"status": "PAUSED"},
    ],
)
async def test_existing_schedule_not_silently_replaced(changes):
    result = await service()._response(uuid4(), preference(**changes))
    assert result.availability == "UNSUPPORTED_SCHEDULE" and not result.can_enable


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["ELDER", "ADMIN", "HOME_CARE_WORKER", "SYSTEM_SERVICE"])
async def test_other_role_denied_before_database_read(role):
    sut = service(role=role)
    with pytest.raises(NotFoundError):
        await sut.get(uuid4())
    sut._session.scalar.assert_not_awaited()


def patch_update(monkeypatch, sut, row=None):
    sut._require_access = AsyncMock(return_value=SimpleNamespace(version=3))
    sut._preference = AsyncMock(return_value=row)
    # Parent lock succeeds; following scalar queries read the LINE identity.
    sut._session.scalar.side_effect = [SimpleNamespace(id=uuid4()), None, None]
    idem = MagicMock()
    idem.begin = AsyncMock(return_value=SimpleNamespace(replayed=False))
    idem.complete = AsyncMock()
    monkeypatch.setattr(
        "app.services.family_notification_preference_service.IdempotencyRepository",
        lambda *args: idem,
    )
    outbox = AsyncMock()
    monkeypatch.setattr(
        "app.services.family_notification_preference_service.write_outbox_entry", outbox
    )
    return idem, outbox


@pytest.mark.asyncio
async def test_disable_preserves_other_channels_and_legacy_schedule(monkeypatch):
    row = preference(frequency="WEEKLY", quiet_hours={"start": "23:00"})
    sut = service(available=False)
    idem, outbox = patch_update(monkeypatch, sut, row)
    result = await sut.update(
        uuid4(),
        UpdateFamilyLineNotificationPreference(line_enabled=False, expected_version=2),
        idempotency_key="own-key",
        trace_id="synthetic",
    )
    assert not result.line_enabled and result.version == 3
    assert row.channels == ["EMAIL"] and row.frequency == "WEEKLY"
    assert row.quiet_hours == {"start": "23:00"} and row.important_event_enabled
    assert outbox.await_args.kwargs["payload"] == {"line_enabled": False, "version": 3}
    assert sut._require_access.await_count == 3
    idem.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_stale_version_has_no_write(monkeypatch):
    row = preference()
    sut = service()
    _, outbox = patch_update(monkeypatch, sut, row)
    with pytest.raises(ConflictError, match="version conflict"):
        await sut.update(
            uuid4(),
            UpdateFamilyLineNotificationPreference(line_enabled=False, expected_version=1),
            idempotency_key="stale",
            trace_id="synthetic",
        )
    assert row.version == 2 and "LINE" in row.channels
    outbox.assert_not_awaited()


@pytest.mark.asyncio
async def test_enable_when_unavailable_has_no_write(monkeypatch):
    sut = service(available=False)
    _, outbox = patch_update(monkeypatch, sut)
    with pytest.raises(ConflictError, match="not ready"):
        await sut.update(
            uuid4(),
            UpdateFamilyLineNotificationPreference(line_enabled=True, expected_version=0),
            idempotency_key="disabled",
            trace_id="synthetic",
        )
    sut._session.add.assert_not_called()
    outbox.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_rechecks_access_and_does_not_duplicate_write(monkeypatch):
    sut = service()
    idem, outbox = patch_update(monkeypatch, sut)
    snapshot = await service(available=False)._response(uuid4(), None)
    idem.begin.return_value = SimpleNamespace(
        replayed=True, response_body=snapshot.model_dump(mode="json")
    )
    result = await sut.update(
        snapshot.elder_id,
        UpdateFamilyLineNotificationPreference(line_enabled=False, expected_version=0),
        idempotency_key="replay",
        trace_id="synthetic",
    )
    assert result == snapshot and sut._require_access.await_count == 3
    sut._preference.assert_not_awaited()
    outbox.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoked_access_during_replay_is_denied(monkeypatch):
    sut = service()
    idem, outbox = patch_update(monkeypatch, sut)
    sut._require_access.side_effect = [
        SimpleNamespace(version=1),
        SimpleNamespace(version=1),
        NotFoundError("Resource not found"),
    ]
    with pytest.raises(NotFoundError):
        await sut.update(
            uuid4(),
            UpdateFamilyLineNotificationPreference(line_enabled=False, expected_version=0),
            idempotency_key="revoked",
            trace_id="synthetic",
        )
    outbox.assert_not_awaited()
    idem.complete.assert_not_awaited()
