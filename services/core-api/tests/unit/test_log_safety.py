"""Unit tests for app/core/log_safety.py.

Covers the two leak shapes the module exists to stop:
- a credential that lives inside a value rather than in its field name (DSN)
- a traceback reaching the general log instead of the controlled sink
"""

from __future__ import annotations

import logging

import pytest

from app.core.log_safety import (
    DIAGNOSTICS_LOGGER_NAME,
    REDACTED,
    diagnostics_logger,
    exception_type_name,
    record_exception,
    redact_dsn,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────

_CREDENTIAL_DSN = "postgresql+asyncpg://dbuser:p%40ss@db.internal.test:5432/kinsun"


class _StubDriverError(Exception):
    """Stand-in for a driver exception whose message quotes the DSN."""


class _CollectingHandler(logging.Handler):
    """Handler standing in for an operator-attached, access-governed sink."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


# ─── DSN redaction ───────────────────────────────────────────────────────────


class TestRedactDsn:
    def test_keeps_only_the_scheme(self) -> None:
        assert redact_dsn(_CREDENTIAL_DSN) == "postgresql+asyncpg://***"

    @pytest.mark.parametrize(
        "credential_part",
        ["dbuser", "p%40ss", "db.internal.test", "5432", "kinsun"],
    )
    def test_authority_and_database_name_never_survive(self, credential_part: str) -> None:
        assert credential_part not in redact_dsn(_CREDENTIAL_DSN)

    def test_value_without_a_scheme_is_dropped_entirely(self) -> None:
        """A malformed DSN must not leak through a parser that cannot read it."""
        assert redact_dsn("host=db.internal.test password=secret") == REDACTED

    def test_empty_value_stays_empty(self) -> None:
        # An unset setting is not a secret; '***' would imply one exists.
        assert redact_dsn("") == ""


# ─── Exception type naming ───────────────────────────────────────────────────


class TestExceptionTypeName:
    def test_builtin_exception_is_unqualified(self) -> None:
        assert exception_type_name(RuntimeError("boom")) == "RuntimeError"

    def test_non_builtin_exception_keeps_its_module(self) -> None:
        """Module qualification keeps same-named driver errors distinguishable."""
        name = exception_type_name(_StubDriverError(_CREDENTIAL_DSN))

        assert name == f"{_StubDriverError.__module__}._StubDriverError"

    def test_name_never_carries_the_exception_message(self) -> None:
        assert "p%40ss" not in exception_type_name(_StubDriverError(_CREDENTIAL_DSN))


# ─── Controlled traceback sink ───────────────────────────────────────────────


class TestDiagnosticsSink:
    def test_sink_is_detached_from_the_root_logger(self) -> None:
        assert diagnostics_logger.name == DIAGNOSTICS_LOGGER_NAME
        assert diagnostics_logger.propagate is False

    def test_traceback_does_not_reach_the_general_log(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """caplog stands in for any handler attached to the root logger."""
        with caplog.at_level(logging.DEBUG):
            record_exception("TEST_CODE", _StubDriverError(_CREDENTIAL_DSN))

        assert caplog.records == []
        assert "p%40ss" not in caplog.text

    def test_traceback_reaches_a_handler_attached_to_the_sink(self) -> None:
        handler = _CollectingHandler()
        diagnostics_logger.addHandler(handler)
        try:
            record_exception(
                "TEST_CODE",
                _StubDriverError("connection refused"),
                correlation_id="cid-1",
            )
        finally:
            diagnostics_logger.removeHandler(handler)

        assert len(handler.records) == 1
        record = handler.records[0]
        assert record.getMessage() == "TEST_CODE"
        assert record.code == "TEST_CODE"
        # The correlation ID is what joins the sink entry to the general log.
        assert record.correlation_id == "cid-1"
        assert record.exc_info is not None
