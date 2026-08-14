"""Deterministic, non-inferential rendering of reviewed care-event facts."""

from __future__ import annotations

from typing import Any

SUMMARY_CATEGORY_BY_EVENT_TYPE = {
    "MEAL": "MEAL",
    "ACTIVITY": "ACTIVITY",
    "ACTIVITY_PARTICIPATION": "ACTIVITY",
    "ACTIVITY_CANCELLED": "ACTIVITY",
    "SLEEP": "SLEEP",
    "MEDICATION_STATEMENT": "MEDICATION_STATEMENT",
    "SOCIAL_CONTACT": "SOCIAL",
    "EXPECTED_CONTACT_MISSED": "SOCIAL",
    "EMOTION_EXPRESSION": "IMPORTANT_EVENT",
    "COMPANIONSHIP_NEED": "IMPORTANT_EVENT",
}

_LABEL_BY_EVENT_TYPE = {
    "MEAL": "飲食紀錄",
    "ACTIVITY": "活動紀錄",
    "ACTIVITY_PARTICIPATION": "活動參與紀錄",
    "ACTIVITY_CANCELLED": "活動取消紀錄",
    "SLEEP": "睡眠陳述",
    "MEDICATION_STATEMENT": "用藥陳述",
    "SOCIAL_CONTACT": "社交聯繫紀錄",
    "EXPECTED_CONTACT_MISSED": "預期聯繫未發生紀錄",
    "EMOTION_EXPRESSION": "情緒表達",
    "COMPANIONSHIP_NEED": "陪伴需求表達",
}


def render_reviewed_event(event_type: str, payload: dict[str, Any]) -> str:
    """Render only an explicit source field, otherwise a neutral presence fact."""

    label = _LABEL_BY_EVENT_TYPE.get(event_type, "已覆核事件")
    for key in ("summary", "content", "description", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            collapsed = " ".join(value.split())[:400]
            return f"{label}：{collapsed}"
    return f"{label}：已有一筆人工覆核紀錄。"
