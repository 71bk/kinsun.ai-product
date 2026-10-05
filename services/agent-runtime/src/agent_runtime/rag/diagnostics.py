"""Content-free, task-local failure diagnostics for the V3 request boundary."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal

import httpx

Stage = Literal["safety", "retrieval", "context", "generation", "validation", "response"]
logger = logging.getLogger(__name__)
_JSON_ERRORS = frozenset(
    {"INVALID_GENERATION_JSON", "DUPLICATE_GENERATION_KEY", "NONFINITE_GENERATION_NUMBER"}
)
_CITATION_ERRORS = frozenset(
    {
        "INVALID_ANSWER_EVIDENCE",
        "INVALID_CITATION_IDS",
        "DUPLICATE_CITATION_ID",
        "UNKNOWN_CITATION_ID",
        "INVALID_SUPPORT_QUOTES",
        "INVALID_SUPPORT_QUOTE",
        "UNSELECTED_QUOTE_CITATION",
        "AMBIGUOUS_SOURCE_LAYOUT",
        "INVALID_SUPPORT_SPAN",
        "UNKNOWN_SUPPORT_SPAN",
        "SUPPORT_QUOTE_NOT_IN_SOURCE",
        "MISSING_CITATION_QUOTE",
    }
)


@dataclass
class FailureDiagnostic:
    request_tag: str
    stage: Stage = "safety"
    code: str | None = None
    started: float = field(default_factory=monotonic)

    def emit(self) -> None:
        if self.code is None:
            return
        # Message JSON remains visible with the default Uvicorn formatter. Never
        # attach exceptions/tracebacks, request objects or arbitrary provider text.
        payload = {
            "event": "rag_v3_failure",
            "request_tag": self.request_tag,
            "stage": self.stage,
            "code": self.code,
            "elapsed_ms": max(0, int((monotonic() - self.started) * 1000)),
        }
        logger.warning("%s", json.dumps(payload, sort_keys=True))


_current: ContextVar[FailureDiagnostic | None] = ContextVar("rag_failure", default=None)


@contextmanager
def failure_diagnostics(request_id: str):
    # Correlate by the first 16 hex characters of SHA-256; never echo caller IDs.
    diagnostic = FailureDiagnostic(hashlib.sha256(request_id.encode()).hexdigest()[:16])
    token = _current.set(diagnostic)
    try:
        yield diagnostic
    finally:
        _current.reset(token)
        diagnostic.emit()


def mark_stage(stage: Stage) -> None:
    if diagnostic := _current.get():
        diagnostic.stage = stage


def record_validation_failure(reason: str) -> None:
    if diagnostic := _current.get():
        if diagnostic.stage == "context":
            diagnostic.code = "CONTEXT_REJECTED"
        elif reason in _JSON_ERRORS:
            diagnostic.code = "JSON_REJECTED"
        elif reason in _CITATION_ERRORS:
            diagnostic.code = "CITATION_REJECTED"
        else:
            diagnostic.code = "VALIDATION_REJECTED"


def record_exception(exc: Exception) -> None:
    if diagnostic := _current.get():
        # SDK wrappers retain the typed cause. Bound traversal and never inspect
        # exception messages (which may contain full prompts or connection URLs).
        cause: BaseException | None = exc
        timed_out = False
        for _ in range(8):
            if cause is None:
                break
            if isinstance(cause, TimeoutError | httpx.TimeoutException):
                timed_out = True
                break
            cause = cause.__cause__
        diagnostic.code = f"{diagnostic.stage.upper()}_{'TIMEOUT' if timed_out else 'FAILED'}"
