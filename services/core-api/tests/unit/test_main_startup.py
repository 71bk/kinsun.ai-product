"""Unit tests for the fatal-startup paths in app/main.py (M-07).

A settings failure is the one startup event whose exception text is guaranteed
to contain a credential: the value most likely to be rejected is DATABASE_URL,
and Pydantic echoes the rejected input. These tests pin that neither the log
entry nor the stderr notice may carry it.
"""

from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.core.config import Settings
from app.main import _invalid_setting_names, _settings_failure_notice, lifespan

# Deliberately short so Pydantic's error rendering cannot truncate the secret
# away and make the canary test below pass for the wrong reason.
_LEAKY_DB_URL = "mysql://u:dbsecret@dbhost/kinsun"


def _rejected_dsn_error() -> ValidationError:
    """Produce the real failure: DATABASE_URL rejected for its driver."""
    env = {"APP_ENV": "development", "DATABASE_URL": _LEAKY_DB_URL}
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(ValidationError) as excinfo:
            Settings(_env_file=None)
    return excinfo.value


def test_pydantic_error_text_echoes_the_rejected_dsn() -> None:
    """Canary for why _invalid_setting_names exists.

    If a future Pydantic stops echoing the rejected input, this test fails and
    the reduction below can be simplified — it is not a regression to fix by
    formatting the exception again.
    """
    assert "dbsecret" in str(_rejected_dsn_error())


def test_invalid_setting_names_reports_the_field_without_its_value() -> None:
    assert _invalid_setting_names(_rejected_dsn_error()) == ["database_url"]


def test_invalid_setting_names_tolerates_a_non_pydantic_error() -> None:
    """An unexpected error shape yields no names rather than quoting itself."""
    assert _invalid_setting_names(RuntimeError("connect failed for u:dbsecret@dbhost")) == []


def test_settings_failure_notice_carries_no_value() -> None:
    notice = _settings_failure_notice(_invalid_setting_names(_rejected_dsn_error()))

    assert notice == "FATAL: Settings validation failed for: database_url"
    assert "dbsecret" not in notice
    assert "dbhost" not in notice


def test_settings_failure_notice_without_locations_is_still_actionable() -> None:
    assert _settings_failure_notice([]) == "FATAL: Settings validation failed for: unknown setting"


@pytest.mark.asyncio
async def test_fatal_startup_names_the_field_but_never_the_value(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = _rejected_dsn_error()

    with patch("app.main.get_settings", side_effect=error):
        with caplog.at_level(logging.CRITICAL, logger="app.main"):
            with pytest.raises(SystemExit) as exit_info:
                async with lifespan(FastAPI()):
                    pass

    assert exit_info.value.code == 1

    record = caplog.records[-1]
    assert record.code == "SETTINGS_VALIDATION_FAILED"
    assert record.invalid_fields == ["database_url"]
    assert not hasattr(record, "error")
    assert record.exc_info is None

    rendered = "\n".join(str(item.__dict__) for item in caplog.records)
    assert "dbsecret" not in rendered

    stderr = capsys.readouterr().err
    assert "database_url" in stderr
    assert "dbsecret" not in stderr
