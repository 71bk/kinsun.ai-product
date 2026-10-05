"""Task-local, content-free generation diagnostics for explicit local evaluation."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from google.genai import errors


@dataclass(frozen=True, slots=True)
class GenerationDiagnostics:
    finish_reason: str | None
    prompt_token_count: int | None
    candidates_token_count: int | None
    thoughts_token_count: int | None
    total_token_count: int | None
    output_chars: int | None
    json_format_category: str
    upstream_exception_type: str | None = None
    upstream_http_status_code: int | None = None
    upstream_reason: str | None = None


_collector: ContextVar[list[GenerationDiagnostics] | None] = ContextVar(
    "generation_diagnostics_collector", default=None
)
_FINISH_REASONS = frozenset(
    {
        "FINISH_REASON_UNSPECIFIED",
        "STOP",
        "MAX_TOKENS",
        "SAFETY",
        "RECITATION",
        "LANGUAGE",
        "OTHER",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "MALFORMED_FUNCTION_CALL",
        "IMAGE_SAFETY",
        "UNEXPECTED_TOOL_CALL",
        "IMAGE_PROHIBITED_CONTENT",
        "NO_IMAGE",
        "IMAGE_RECITATION",
        "IMAGE_OTHER",
    }
)


@contextmanager
def capture_generation_diagnostics() -> Iterator[list[GenerationDiagnostics]]:
    """Capture only this context's calls; reset even when generation raises."""
    records: list[GenerationDiagnostics] = []
    token = _collector.set(records)
    try:
        yield records
    finally:
        _collector.reset(token)


def _count(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 1_000_000_000 else None


def _reject_constant(value: str):
    raise ValueError("nonfinite JSON")


def _category(content: Any) -> str:
    if not isinstance(content, str):
        return "UNAVAILABLE"
    if not content.strip():
        return "EMPTY"
    if content.lstrip().startswith("```"):
        return "CODE_FENCED_JSON"
    try:
        parsed = json.loads(content, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return "INVALID_JSON"
    return "VALID_JSON_OBJECT" if isinstance(parsed, dict) else "VALID_JSON_OTHER"


def _safe_attr(value: Any, name: str, default=None):
    try:
        return getattr(value, name, default)
    except Exception:
        return default


def record_generation_diagnostics(response: Any) -> None:
    collector = _collector.get()
    if collector is None:
        return
    try:
        content = response.text
    except Exception:
        content = None
    candidates = _safe_attr(response, "candidates", None)
    reason = (
        _safe_attr(candidates[0], "finish_reason", None)
        if isinstance(candidates, list | tuple) and candidates
        else None
    )
    reason = _safe_attr(reason, "value", reason)
    safe_reason = (
        reason
        if isinstance(reason, str) and reason in _FINISH_REASONS
        else ("UNKNOWN" if reason is not None else None)
    )
    usage = _safe_attr(response, "usage_metadata", None)
    collector.append(
        GenerationDiagnostics(
            finish_reason=safe_reason,
            prompt_token_count=_count(_safe_attr(usage, "prompt_token_count", None)),
            candidates_token_count=_count(_safe_attr(usage, "candidates_token_count", None)),
            thoughts_token_count=_count(_safe_attr(usage, "thoughts_token_count", None)),
            total_token_count=_count(_safe_attr(usage, "total_token_count", None)),
            output_chars=len(content) if isinstance(content, str) else None,
            json_format_category=_category(content),
        )
    )


def record_generation_failure(exception: Exception) -> None:
    """Record bounded SDK failure identity, never exception messages or payloads."""
    collector = _collector.get()
    if collector is None:
        return
    exception_type = "UNKNOWN"
    for known_type in (errors.ClientError, errors.ServerError, errors.APIError):
        if type(exception) is known_type:
            exception_type = known_type.__name__
            break
    code = _safe_attr(exception, "code", None)
    status = code if type(code) is int and 100 <= code <= 599 else None
    reason = None
    if status == 400:
        message = _safe_attr(exception, "message", None)
        message = message.lower() if isinstance(message, str) else ""
        if "schema" in message:
            reason = (
                "SCHEMA_COMPLEXITY"
                if "too many states" in message or "too complex" in message
                else "SCHEMA_REQUEST_REJECTED"
            )
        else:
            reason = "INVALID_PROVIDER_REQUEST"
    collector.append(
        GenerationDiagnostics(
            finish_reason=None,
            prompt_token_count=None,
            candidates_token_count=None,
            thoughts_token_count=None,
            total_token_count=None,
            output_chars=None,
            json_format_category="UNAVAILABLE",
            upstream_exception_type=exception_type,
            upstream_http_status_code=status,
            upstream_reason=reason,
        )
    )
