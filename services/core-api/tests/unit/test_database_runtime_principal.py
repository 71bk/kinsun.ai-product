"""Tests for the fail-closed staging PostgreSQL runtime principal."""

from __future__ import annotations

from typing import Any

import pytest

import app.models  # noqa: F401
from app.database_runtime_principal import (
    PROTECTED_COLUMN_UPDATE_DENY_MATRIX,
    PROTECTED_TABLE_DENY_MATRIX,
    RUNTIME_COLUMN_UPDATE_PRIVILEGES,
    RUNTIME_TABLE_PRIVILEGES,
    RUNTIME_USERNAME,
    RuntimeCredential,
    RuntimePrincipalConfigurationError,
    RuntimePrincipalInvariantError,
    load_runtime_credential,
    reconcile_runtime_principal,
)
from app.db.base import SCHEMA_NAME, Base

RUNTIME_PASSWORD = "synthetic-runtime-password-material-000000000001"


class _FakePgConnection:
    def encrypt_password(
        self, password: bytes, username: bytes, algorithm: bytes | None = None
    ) -> bytes:
        assert password == RUNTIME_PASSWORD.encode()
        assert username == RUNTIME_USERNAME.encode()
        assert algorithm == b"scram-sha-256"
        return b"SCRAM-SHA-256$synthetic-verifier-only"


class _FakeCursor:
    def __init__(
        self,
        responses: list[tuple[Any, ...]],
        type_rows: list[tuple[str]] | None = None,
        sequence_rows: list[tuple[str, str]] | None = None,
        column_rows: list[tuple[str, list[str]]] | None = None,
    ) -> None:
        self._responses = iter(responses)
        self._fetchall_responses = iter(
            [
                [] if column_rows is None else column_rows,
                [] if sequence_rows is None else sequence_rows,
                [("consent_status",)] if type_rows is None else type_rows,
            ]
        )
        self.executions: list[tuple[str, object | None]] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: object, params: object | None = None) -> None:
        rendered = query.as_string() if hasattr(query, "as_string") else str(query)
        self.executions.append((rendered, params))

    def fetchone(self) -> tuple[Any, ...]:
        return next(self._responses)

    def fetchall(self) -> list[tuple[Any, ...]]:
        return next(self._fetchall_responses)


class _FakeConnection:
    def __init__(
        self,
        responses: list[tuple[Any, ...]],
        type_rows: list[tuple[str]] | None = None,
        sequence_rows: list[tuple[str, str]] | None = None,
        column_rows: list[tuple[str, list[str]]] | None = None,
    ) -> None:
        self.pgconn = _FakePgConnection()
        self.cursor_instance = _FakeCursor(responses, type_rows, sequence_rows, column_rows)

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self.cursor_instance


def _credential() -> RuntimeCredential:
    return RuntimeCredential(RUNTIME_USERNAME, RUNTIME_PASSWORD)


def test_runtime_credential_is_fixed_and_password_is_redacted_from_repr() -> None:
    credential = load_runtime_credential(
        {
            "DB_RUNTIME_USERNAME": RUNTIME_USERNAME,
            "DB_RUNTIME_PASSWORD": RUNTIME_PASSWORD,
        }
    )

    assert credential.username == RUNTIME_USERNAME
    assert credential.password == RUNTIME_PASSWORD
    assert RUNTIME_PASSWORD not in repr(credential)


@pytest.mark.parametrize(
    "username",
    ["", "kinsun_admin", 'kinsun_app" SUPERUSER', "KINSUN_APP", "kinsun-app"],
)
def test_unexpected_or_unsafe_runtime_identifier_fails_closed(username: str) -> None:
    with pytest.raises(RuntimePrincipalConfigurationError, match="DB_RUNTIME_USERNAME"):
        load_runtime_credential(
            {"DB_RUNTIME_USERNAME": username, "DB_RUNTIME_PASSWORD": RUNTIME_PASSWORD}
        )


@pytest.mark.parametrize("password", ["", "too-short", "x" * 31, "x" * 1025, "x" * 32 + "\x00"])
def test_invalid_runtime_password_fails_without_echoing_value(password: str) -> None:
    with pytest.raises(RuntimePrincipalConfigurationError) as exc_info:
        load_runtime_credential(
            {"DB_RUNTIME_USERNAME": RUNTIME_USERNAME, "DB_RUNTIME_PASSWORD": password}
        )

    assert "DB_RUNTIME_PASSWORD" in str(exc_info.value)
    if password:
        assert password not in str(exc_info.value)


def test_new_role_is_created_with_explicit_table_privilege_matrix() -> None:
    connection = _FakeConnection(
        [
            ('migration"owner', "kinsun"),
            (True,),  # eldercare_ai exists after Alembic
            (False,),  # runtime role is new
        ],
        column_rows=[("consent_grant", ["elder_id", "status"])],
    )

    captured_dsn = ""

    def fake_connect(dsn: str) -> _FakeConnection:
        nonlocal captured_dsn
        captured_dsn = dsn
        return connection

    reconcile_runtime_principal(
        "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
        _credential(),
        connect=fake_connect,
    )

    assert captured_dsn == "postgresql://admin:never-log@db.invalid/kinsun"
    sql_text = "\n".join(query for query, _ in connection.cursor_instance.executions)
    assert RUNTIME_PASSWORD not in sql_text
    assert 'CREATE ROLE "kinsun_app" WITH LOGIN PASSWORD' in sql_text
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS" in sql_text
    assert 'GRANT SELECT ON TABLE "eldercare_ai"."policy_registry" TO "kinsun_app"' in sql_text
    assert (
        'GRANT SELECT, INSERT ON TABLE "eldercare_ai"."consent_grant" TO "kinsun_app"' in sql_text
    )
    assert (
        "GRANT SELECT, INSERT, DELETE ON TABLE "
        '"eldercare_ai"."idempotency_record" TO "kinsun_app"' in sql_text
    )
    assert (
        'GRANT UPDATE ("status", "revoked_at", "updated_at") ON TABLE '
        '"eldercare_ai"."consent_grant" TO "kinsun_app"' in sql_text
    )
    assert (
        'REVOKE ALL PRIVILEGES ("elder_id", "status") ON TABLE '
        '"eldercare_ai"."consent_grant" FROM "kinsun_app"' in sql_text
    )
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES" not in sql_text
    assert "GRANT USAGE, SELECT ON ALL SEQUENCES" not in sql_text
    assert 'GRANT SELECT ON TABLE "eldercare_ai"."audit_record"' not in sql_text
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO" not in sql_text
    assert "GRANT USAGE, SELECT ON SEQUENCES TO" not in sql_text
    assert 'GRANT USAGE ON TYPE "eldercare_ai"."consent_status" TO "kinsun_app"' in sql_text
    assert "ON ALL TYPES IN SCHEMA" not in sql_text
    assert 'FOR ROLE "migration""owner" IN SCHEMA "eldercare_ai"' in sql_text
    assert "GRANT CREATE" not in sql_text
    assert "GRANT TRUNCATE" not in sql_text
    assert "GRANT TRIGGER" not in sql_text
    assert "GRANT EXECUTE" not in sql_text


def test_runtime_privilege_contract_denies_sensitive_mutation() -> None:
    assert "audit_record" not in RUNTIME_TABLE_PRIVILEGES
    assert RUNTIME_TABLE_PRIVILEGES["policy_registry"] == ("SELECT",)
    assert "DELETE" not in RUNTIME_TABLE_PRIVILEGES["consent_grant"]
    assert "DELETE" not in RUNTIME_TABLE_PRIVILEGES["outbox_event"]
    assert RUNTIME_TABLE_PRIVILEGES["idempotency_record"] == (
        "SELECT",
        "INSERT",
        "DELETE",
    )
    assert RUNTIME_COLUMN_UPDATE_PRIVILEGES["consent_grant"] == (
        "status",
        "revoked_at",
        "updated_at",
    )
    assert "elder_id" in PROTECTED_COLUMN_UPDATE_DENY_MATRIX["consent_grant"]
    assert PROTECTED_TABLE_DENY_MATRIX["audit_record"] == (
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    )
    assert RUNTIME_COLUMN_UPDATE_PRIVILEGES["password_credential"] == (
        "password_hash",
        "parameter_version",
        "status",
        "failed_attempt_count",
        "locked_until",
        "password_changed_at",
        "last_verified_at",
        "revoked_at",
        "version",
        "updated_at",
    )
    assert PROTECTED_COLUMN_UPDATE_DENY_MATRIX["password_credential"] == (
        "actor_id",
        "algorithm",
    )
    assert "expires_at" in RUNTIME_COLUMN_UPDATE_PRIVILEGES["line_link_challenge"]
    assert "event_type" in RUNTIME_COLUMN_UPDATE_PRIVILEGES["line_webhook_receipt"]
    assert RUNTIME_TABLE_PRIVILEGES["context_manifest"] == ("SELECT",)
    assert RUNTIME_TABLE_PRIVILEGES["knowledge_source"] == ("SELECT",)
    assert RUNTIME_TABLE_PRIVILEGES["knowledge_source_version"] == ("SELECT",)


def test_runtime_privilege_allowlist_matches_orm_table_and_column_names() -> None:
    orm_tables = {
        table.name: table for table in Base.metadata.tables.values() if table.schema == SCHEMA_NAME
    }

    assert set(RUNTIME_TABLE_PRIVILEGES) <= set(orm_tables)
    for table_name, columns in RUNTIME_COLUMN_UPDATE_PRIVILEGES.items():
        assert table_name in RUNTIME_TABLE_PRIVILEGES
        assert "UPDATE" not in RUNTIME_TABLE_PRIVILEGES[table_name]
        assert set(columns) <= set(orm_tables[table_name].columns.keys())
    for table_name, columns in PROTECTED_COLUMN_UPDATE_DENY_MATRIX.items():
        assert table_name in RUNTIME_COLUMN_UPDATE_PRIVILEGES
        assert set(columns).isdisjoint(RUNTIME_COLUMN_UPDATE_PRIVILEGES[table_name])
        assert set(columns) <= set(orm_tables[table_name].columns.keys())


def test_only_sequences_owned_by_insert_allowlisted_tables_are_granted() -> None:
    connection = _FakeConnection(
        [
            ("kinsun_admin", "kinsun"),
            (True,),
            (False,),
        ],
        sequence_rows=[("eldercare_ai", "synthetic_owned_sequence")],
    )

    reconcile_runtime_principal(
        "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
        _credential(),
        connect=lambda _: connection,
    )

    sql_text = "\n".join(query for query, _ in connection.cursor_instance.executions)
    assert (
        'GRANT USAGE, SELECT ON SEQUENCE "eldercare_ai"."synthetic_owned_sequence" '
        'TO "kinsun_app"' in sql_text
    )


@pytest.mark.parametrize(
    ("safety_responses", "expected_message"),
    [
        ([(True,)], "membership"),
        ([(False,), (True,)], "owns"),
    ],
)
def test_existing_role_with_privilege_invariants_fails_before_alter(
    safety_responses: list[tuple[bool]], expected_message: str
) -> None:
    connection = _FakeConnection(
        [
            ("kinsun_admin", "kinsun"),
            (True,),
            (True,),  # runtime role already exists
            *safety_responses,
        ]
    )

    with pytest.raises(RuntimePrincipalInvariantError, match=expected_message):
        reconcile_runtime_principal(
            "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
            _credential(),
            connect=lambda _: connection,
        )

    sql_text = "\n".join(query for query, _ in connection.cursor_instance.executions)
    assert 'ALTER ROLE "kinsun_app"' not in sql_text
    assert RUNTIME_PASSWORD not in sql_text


def test_existing_role_membership_check_is_bidirectional() -> None:
    connection = _FakeConnection(
        [
            ("kinsun_admin", "kinsun"),
            (True,),
            (True,),  # runtime role already exists
            (False,),  # no membership in either direction
            (False,),  # no ownership
        ]
    )

    reconcile_runtime_principal(
        "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
        _credential(),
        connect=lambda _: connection,
    )

    membership_query, membership_params = connection.cursor_instance.executions[4]
    assert "memberships.member" in membership_query
    assert "memberships.roleid" in membership_query
    assert membership_params == (RUNTIME_USERNAME, RUNTIME_USERNAME)


def test_missing_schema_fails_before_role_creation() -> None:
    connection = _FakeConnection([("kinsun_admin", "kinsun"), (False,)])

    with pytest.raises(RuntimePrincipalInvariantError, match="schema does not exist"):
        reconcile_runtime_principal(
            "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
            _credential(),
            connect=lambda _: connection,
        )

    sql_text = "\n".join(query for query, _ in connection.cursor_instance.executions)
    assert "CREATE ROLE" not in sql_text


def test_admin_and_runtime_identity_collision_fails_closed() -> None:
    connection = _FakeConnection([(RUNTIME_USERNAME, "kinsun")])

    with pytest.raises(RuntimePrincipalInvariantError, match="identical"):
        reconcile_runtime_principal(
            "postgresql+psycopg://admin:never-log@db.invalid/kinsun",
            _credential(),
            connect=lambda _: connection,
        )
