"""PostgreSQL 16 integration proof for the Core runtime principal."""

from __future__ import annotations

import os
from urllib.parse import quote

import psycopg
import pytest
from psycopg import sql

from app.database_runtime_principal import (
    PROTECTED_COLUMN_UPDATE_DENY_MATRIX,
    PROTECTED_SHARED_TABLE_DENY_MATRIX,
    PROTECTED_TABLE_DENY_MATRIX,
    RUNTIME_COLUMN_UPDATE_PRIVILEGES,
    RUNTIME_SHARED_SCHEMA_PRIVILEGES,
    RUNTIME_TABLE_PRIVILEGES,
    RUNTIME_USERNAME,
    RuntimeCredential,
    reconcile_runtime_principal,
)

_DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun_test"
)
_RUNTIME_PASSWORD = "synthetic-integration-runtime-password-000000000001"
_CURRENT_TABLE = "runtime_principal_current_probe"
_FUTURE_TABLE = "runtime_principal_future_probe"
_CURRENT_TYPE = "runtime_principal_current_state"
_FUTURE_TYPE = "runtime_principal_future_state"


def _admin_urls() -> tuple[str, str]:
    async_url = os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)
    sqlalchemy_url = async_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    psycopg_url = sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://")
    return sqlalchemy_url, psycopg_url


def _runtime_url(admin_psycopg_url: str) -> str:
    authority_and_path = admin_psycopg_url.split("@", 1)[1]
    return (
        f"postgresql://{quote(RUNTIME_USERNAME, safe='')}:"
        f"{quote(_RUNTIME_PASSWORD, safe='')}@{authority_and_path}"
    )


def _drop_probes(cursor: psycopg.Cursor) -> None:
    cursor.execute(f'DROP TABLE IF EXISTS eldercare_ai."{_FUTURE_TABLE}"')
    cursor.execute(f'DROP TABLE IF EXISTS eldercare_ai."{_CURRENT_TABLE}"')
    cursor.execute(f'DROP TYPE IF EXISTS eldercare_ai."{_FUTURE_TYPE}"')
    cursor.execute(f'DROP TYPE IF EXISTS eldercare_ai."{_CURRENT_TYPE}"')


def _runtime_role_exists(cursor: psycopg.Cursor) -> bool:
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
        (RUNTIME_USERNAME,),
    )
    return bool(cursor.fetchone()[0])


def _drop_test_runtime_role(cursor: psycopg.Cursor) -> None:
    """Remove grants and the cluster-wide role created by this isolated test."""
    cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(RUNTIME_USERNAME)))
    cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(RUNTIME_USERNAME)))


@pytest.mark.usefixtures("run_migrations")
def test_runtime_role_enforces_explicit_permission_and_deny_matrix() -> None:
    sqlalchemy_admin_url, psycopg_admin_url = _admin_urls()
    role_created_by_test = False

    with psycopg.connect(psycopg_admin_url) as admin_connection:
        with admin_connection.cursor() as cursor:
            if _runtime_role_exists(cursor):
                pytest.skip(
                    "runtime-principal integration requires an isolated cluster "
                    "without a pre-existing kinsun_app role"
                )

    try:
        with psycopg.connect(psycopg_admin_url) as admin_connection:
            with admin_connection.cursor() as cursor:
                _drop_probes(cursor)
                cursor.execute(f"CREATE TYPE eldercare_ai.\"{_CURRENT_TYPE}\" AS ENUM ('ready')")
                cursor.execute(
                    f"""
                    CREATE TABLE eldercare_ai."{_CURRENT_TABLE}" (
                        id bigserial PRIMARY KEY,
                        value text NOT NULL,
                        state eldercare_ai."{_CURRENT_TYPE}" NOT NULL
                    )
                    """
                )

        reconcile_runtime_principal(
            sqlalchemy_admin_url,
            RuntimeCredential(RUNTIME_USERNAME, _RUNTIME_PASSWORD),
        )
        role_created_by_test = True

        # A table created after reconciliation must remain inaccessible until the
        # application privilege matrix explicitly classifies it.
        with psycopg.connect(psycopg_admin_url) as admin_connection:
            with admin_connection.cursor() as cursor:
                cursor.execute(f"CREATE TYPE eldercare_ai.\"{_FUTURE_TYPE}\" AS ENUM ('ready')")
                cursor.execute(
                    f"""
                    CREATE TABLE eldercare_ai."{_FUTURE_TABLE}" (
                        id bigserial PRIMARY KEY,
                        value text NOT NULL,
                        state eldercare_ai."{_FUTURE_TYPE}" NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    SELECT rolsuper, rolcreatedb, rolcreaterole, rolinherit,
                           rolreplication, rolbypassrls
                      FROM pg_roles
                     WHERE rolname = %s
                    """,
                    (RUNTIME_USERNAME,),
                )
                assert cursor.fetchone() == (False, False, False, False, False, False)
                cursor.execute(
                    "SELECT has_schema_privilege(%s, 'eldercare_ai', 'USAGE'), "
                    "has_schema_privilege(%s, 'eldercare_ai', 'CREATE')",
                    (RUNTIME_USERNAME, RUNTIME_USERNAME),
                )
                assert cursor.fetchone() == (True, False)

                for table_name, privileges in RUNTIME_TABLE_PRIVILEGES.items():
                    for privilege in privileges:
                        cursor.execute(
                            "SELECT has_table_privilege(%s, %s, %s)",
                            (
                                RUNTIME_USERNAME,
                                f"eldercare_ai.{table_name}",
                                privilege,
                            ),
                        )
                        assert cursor.fetchone() == (True,), (table_name, privilege)

                for table_name, columns in RUNTIME_COLUMN_UPDATE_PRIVILEGES.items():
                    for column in columns:
                        cursor.execute(
                            "SELECT has_column_privilege(%s, %s, %s, 'UPDATE')",
                            (RUNTIME_USERNAME, f"eldercare_ai.{table_name}", column),
                        )
                        assert cursor.fetchone() == (True,), (table_name, column)

                    cursor.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'eldercare_ai' AND table_name = %s",
                        (table_name,),
                    )
                    allowed_columns = set(columns)
                    for (column,) in cursor.fetchall():
                        if column in allowed_columns:
                            continue
                        cursor.execute(
                            "SELECT has_column_privilege(%s, %s, %s, 'UPDATE')",
                            (RUNTIME_USERNAME, f"eldercare_ai.{table_name}", column),
                        )
                        assert cursor.fetchone() == (False,), (table_name, column)

                for table_name, denied_privileges in PROTECTED_TABLE_DENY_MATRIX.items():
                    for privilege in denied_privileges:
                        cursor.execute(
                            "SELECT has_table_privilege(%s, %s, %s)",
                            (
                                RUNTIME_USERNAME,
                                f"eldercare_ai.{table_name}",
                                privilege,
                            ),
                        )
                        assert cursor.fetchone() == (False,), (table_name, privilege)

                for table_name, columns in PROTECTED_COLUMN_UPDATE_DENY_MATRIX.items():
                    for column in columns:
                        cursor.execute(
                            "SELECT has_column_privilege(%s, %s, %s, 'UPDATE')",
                            (RUNTIME_USERNAME, f"eldercare_ai.{table_name}", column),
                        )
                        assert cursor.fetchone() == (False,), (table_name, column)

                for schema_name, shared_tables in RUNTIME_SHARED_SCHEMA_PRIVILEGES.items():
                    cursor.execute(
                        "SELECT has_schema_privilege(%s, %s, 'USAGE'), "
                        "has_schema_privilege(%s, %s, 'CREATE')",
                        (RUNTIME_USERNAME, schema_name, RUNTIME_USERNAME, schema_name),
                    )
                    assert cursor.fetchone() == (True, False), schema_name
                    for table_name, privileges in shared_tables.items():
                        for privilege in privileges:
                            cursor.execute(
                                "SELECT has_table_privilege(%s, %s, %s)",
                                (RUNTIME_USERNAME, f"{schema_name}.{table_name}", privilege),
                            )
                            assert cursor.fetchone() == (True,), (table_name, privilege)

                for schema_name, shared_tables in PROTECTED_SHARED_TABLE_DENY_MATRIX.items():
                    for table_name, denied_privileges in shared_tables.items():
                        for privilege in denied_privileges:
                            cursor.execute(
                                "SELECT has_table_privilege(%s, %s, %s)",
                                (RUNTIME_USERNAME, f"{schema_name}.{table_name}", privilege),
                            )
                            assert cursor.fetchone() == (False,), (table_name, privilege)

                cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'eldercare_ai'")
                for (table_name,) in cursor.fetchall():
                    if table_name in RUNTIME_TABLE_PRIVILEGES:
                        continue
                    cursor.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (
                            RUNTIME_USERNAME,
                            f"eldercare_ai.{table_name}",
                            "SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER",
                        ),
                    )
                    assert cursor.fetchone() == (False,), table_name

                for table_name in (_CURRENT_TABLE, _FUTURE_TABLE):
                    cursor.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (
                            RUNTIME_USERNAME,
                            f"eldercare_ai.{table_name}",
                            "SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER",
                        ),
                    )
                    assert cursor.fetchone() == (False,), table_name
                    cursor.execute(
                        "SELECT has_sequence_privilege(%s, "
                        "pg_get_serial_sequence(%s, 'id'), 'USAGE,SELECT,UPDATE')",
                        (RUNTIME_USERNAME, f"eldercare_ai.{table_name}"),
                    )
                    assert cursor.fetchone() == (False,), table_name

        with psycopg.connect(_runtime_url(psycopg_admin_url)) as runtime_connection:
            with runtime_connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM eldercare_ai.policy_registry")
                assert cursor.fetchone()[0] >= 0

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime_connection.cursor() as cursor:
                    cursor.execute("CREATE TABLE eldercare_ai.runtime_principal_forbidden (id int)")
            runtime_connection.rollback()

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime_connection.cursor() as cursor:
                    cursor.execute(f'TRUNCATE eldercare_ai."{_CURRENT_TABLE}"')
            runtime_connection.rollback()

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime_connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO eldercare_ai.audit_record "
                        "(action_type, target_type, result, trace_id) "
                        "VALUES ('probe', 'probe', 'SUCCESS', 'probe')"
                    )
            runtime_connection.rollback()

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime_connection.cursor() as cursor:
                    cursor.execute("DELETE FROM eldercare_ai.consent_grant WHERE FALSE")
            runtime_connection.rollback()

            with runtime_connection.cursor() as cursor:
                cursor.execute("UPDATE eldercare_ai.consent_grant SET status = status WHERE FALSE")
                cursor.execute(
                    "UPDATE eldercare_ai.password_credential "
                    "SET password_hash = password_hash, "
                    "parameter_version = parameter_version, "
                    "password_changed_at = password_changed_at WHERE FALSE"
                )
            runtime_connection.commit()

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime_connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE eldercare_ai.consent_grant SET elder_id = elder_id WHERE FALSE"
                    )
            runtime_connection.rollback()

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime_connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE eldercare_ai.policy_registry SET status = status WHERE FALSE"
                    )
            runtime_connection.rollback()

            # The runtime role claims and purges nonces but can never rewrite one.
            with runtime_connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO service_identity.credential_nonce "
                    "(audience, credential_id, issuer, subject, expires_at) "
                    "VALUES ('agent-runtime', 'runtime-principal-probe', 'kinsun-local', "
                    "'core-api', now() - interval '1 second')"
                )
                cursor.execute(
                    "DELETE FROM service_identity.credential_nonce WHERE expires_at < now()"
                )
            runtime_connection.commit()

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime_connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE service_identity.credential_nonce "
                        "SET expires_at = expires_at WHERE FALSE"
                    )
            runtime_connection.rollback()
    finally:
        with psycopg.connect(psycopg_admin_url) as admin_connection:
            with admin_connection.cursor() as cursor:
                _drop_probes(cursor)
                if role_created_by_test and _runtime_role_exists(cursor):
                    _drop_test_runtime_role(cursor)
