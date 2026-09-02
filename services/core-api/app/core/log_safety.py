"""What may reach a general log line, and where tracebacks are allowed to go.

Two leak shapes motivate this module, both on the AGENTS.md §4 zero-tolerance
list ("Secret、Token、完整 Prompt、完整 Transcript／Audio 出現在一般 Log"):

1. A value can be sensitive without its field name saying so. A PostgreSQL DSN
   carries the password inside the value and names the database host in its
   authority, so the name-substring redaction in ``app.core.config`` cannot
   reach it. ``redact_dsn`` redacts by shape instead.
2. A traceback is the most likely single carrier of restricted data. SQLAlchemy
   and asyncpg frames quote the failing statement and the connection URL, and a
   Pydantic ``ValidationError`` echoes the rejected input, so one
   ``exc_info=True`` on an application logger can place database credentials
   next to ordinary request lines.

The general log therefore keeps only what an on-call engineer needs in order to
decide whether to look further — the exception type, a stable internal code and
the correlation ID — while the traceback goes to ``app.diagnostics``, a logger
that deliberately does not propagate and ships with no handler of its own.
Nothing is written there until an operator attaches a handler whose destination
is governed like restricted data.
"""

from __future__ import annotations

import logging

REDACTED = "***"

DIAGNOSTICS_LOGGER_NAME = "app.diagnostics"

diagnostics_logger = logging.getLogger(DIAGNOSTICS_LOGGER_NAME)
# Propagation is exactly how a traceback would reach the general log, so this
# sink is detached from the root logger. The NullHandler then keeps logging's
# last-resort handler — which writes to stderr — from becoming that sink.
diagnostics_logger.propagate = False
diagnostics_logger.addHandler(logging.NullHandler())


def redact_dsn(dsn: str) -> str:
    """Return a connection string reduced to its scheme.

    Only the scheme is worth keeping: it is what ``Settings.validate_database_url``
    rejects, so it is the one part an operator needs when a URL is refused.
    Everything after it — user name, password, host, port and database name — is
    dropped wholesale rather than parsed, because a malformed DSN must not be
    able to leak through a parser that fails to recognise its shape.
    """
    if not dsn:
        return dsn

    scheme, separator, _authority_and_path = dsn.partition("://")
    if not separator:
        # Not URL-shaped, so no part of it can be assumed safe to keep.
        return REDACTED
    return f"{scheme}://{REDACTED}"


def exception_type_name(exc: BaseException) -> str:
    """Return the qualified exception type, which carries no runtime values."""
    exception_type = type(exc)
    if exception_type.__module__ in {"builtins", "__main__"}:
        return exception_type.__qualname__
    return f"{exception_type.__module__}.{exception_type.__qualname__}"


def record_exception(code: str, exc: BaseException, **context: object) -> None:
    """Send one traceback to the controlled sink under a stable internal code.

    The same ``code`` is emitted on the general log next to the exception type
    and the correlation ID, so an engineer with access to the sink can join the
    two without the traceback ever entering ordinary log storage.
    """
    diagnostics_logger.error(code, exc_info=exc, extra={"code": code, **context})
