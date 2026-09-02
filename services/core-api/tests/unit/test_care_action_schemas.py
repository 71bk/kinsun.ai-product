"""Strict Care Action request boundaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.care_action import CreateCareActionRequest, UpdateCareActionRequest


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(days=1)


def test_create_requires_unique_formal_event_references() -> None:
    event_id = uuid4()

    with pytest.raises(ValidationError, match="must not contain duplicates"):
        CreateCareActionRequest(
            action_type="CONTACT_ELDER",
            title="關心早餐狀況",
            trigger_reason="已覆核事件需要後續確認",
            related_event_ids=[event_id, event_id],
            due_at=_future(),
        )


def test_create_rejects_medical_action_types_and_extra_scope_claims() -> None:
    with pytest.raises(ValidationError):
        CreateCareActionRequest.model_validate(
            {
                "action_type": "CHANGE_MEDICATION",
                "title": "修改藥物",
                "trigger_reason": "不允許的醫療動作",
                "related_event_ids": [str(uuid4())],
                "due_at": _future().isoformat(),
                "expected_elder_scope": "care_action:create",
            }
        )


@pytest.mark.parametrize("field", ["title", "trigger_reason"])
def test_create_rejects_whitespace_only_required_text(field: str) -> None:
    payload = {
        "action_type": "FOLLOW_UP",
        "title": "追蹤午餐狀況",
        "trigger_reason": "已覆核事件需要後續確認",
        "related_event_ids": [uuid4()],
        "due_at": _future(),
    }
    payload[field] = "   "

    with pytest.raises(ValidationError, match="non-whitespace"):
        CreateCareActionRequest.model_validate(payload)


@pytest.mark.parametrize("status", ["COMPLETED", "POSTPONED", "CANCELLED"])
def test_terminal_or_deferred_updates_require_a_reason(status: str) -> None:
    with pytest.raises(ValidationError, match="resolution is required"):
        UpdateCareActionRequest(
            status=status,
            expected_version=1,
            due_at=_future() if status == "POSTPONED" else None,
        )


def test_postponed_update_requires_a_new_due_date() -> None:
    with pytest.raises(ValidationError, match="due_at is required"):
        UpdateCareActionRequest(
            status="POSTPONED",
            expected_version=1,
            resolution="長者今日外出，改期追蹤",
        )
