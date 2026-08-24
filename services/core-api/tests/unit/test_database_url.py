"""Tests for driver-specific PostgreSQL URL normalization."""

from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from app.database_url import to_psycopg_conninfo, to_psycopg_database_url


def test_asyncpg_url_is_converted_to_psycopg_without_hiding_password() -> None:
    converted = to_psycopg_database_url("postgresql+asyncpg://user:p%40ss@db.example.test:5432/app")

    parsed = make_url(converted)
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.username == "user"
    assert parsed.password == "p@ss"
    assert parsed.host == "db.example.test"


def test_asyncpg_ssl_option_becomes_psycopg_sslmode() -> None:
    converted = to_psycopg_database_url(
        "postgresql+asyncpg://user:pass@db.example.test/app?ssl=require"
    )

    parsed = make_url(converted)
    assert "ssl" not in parsed.query
    assert parsed.query["sslmode"] == "require"


def test_existing_compatible_sslmode_and_other_options_are_preserved() -> None:
    converted = to_psycopg_database_url(
        "postgresql+asyncpg://user:pass@db.example.test/app"
        "?ssl=require&sslmode=require&application_name=kinsun"
    )

    parsed = make_url(converted)
    assert parsed.query["sslmode"] == "require"
    assert parsed.query["application_name"] == "kinsun"


def test_conflicting_tls_modes_fail_closed() -> None:
    with pytest.raises(ValueError, match="conflicting TLS modes"):
        to_psycopg_database_url(
            "postgresql+asyncpg://user:pass@db.example.test/app" "?ssl=require&sslmode=disable"
        )


def test_non_postgresql_driver_is_rejected() -> None:
    with pytest.raises(ValueError, match="supported PostgreSQL driver"):
        to_psycopg_database_url("mysql://user:pass@db.example.test/app")


def test_direct_psycopg_conninfo_uses_libpq_scheme_and_preserves_tls() -> None:
    converted = to_psycopg_conninfo(
        "postgresql+asyncpg://user:p%40ss@db.example.test:5432/app?ssl=require"
    )

    parsed = make_url(converted)
    assert parsed.drivername == "postgresql"
    assert parsed.password == "p@ss"
    assert parsed.query["sslmode"] == "require"
