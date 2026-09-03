"""Reconcile the least-privilege PostgreSQL principal used by Core API.

This module is intentionally migration-only.  The long-lived API container never
receives the Aurora administrator credential and cannot call this code successfully.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import psycopg
from psycopg import sql

RUNTIME_SCHEMA = "eldercare_ai"
RUNTIME_USERNAME = "kinsun_app"
_RUNTIME_USERNAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_PROVISIONING_LOCK_ID = 5_409_566_445_540_616_549

_READ_ONLY = ("SELECT",)
_APPEND_ONLY = ("SELECT", "INSERT")
_READ_WRITE = ("SELECT", "INSERT", "UPDATE")
_READ_APPEND_DELETE = ("SELECT", "INSERT", "DELETE")

# Keep this list explicit.  A newly migrated table receives no runtime DML until its
# access pattern is reviewed and added here.  In particular, audit_record and the
# not-yet-implemented baseline surfaces intentionally have no runtime grants.
RUNTIME_TABLE_PRIVILEGES: dict[str, tuple[str, ...]] = {
    # Migration/bootstrap-owned reference data.
    "care_unit": _READ_ONLY,
    "context_manifest": _READ_ONLY,
    "decision_support_profile": _READ_ONLY,
    "knowledge_source": _READ_ONLY,
    "knowledge_source_version": _READ_ONLY,
    "policy_registry": _READ_ONLY,
    # Immutable evidence/version rows written by the application.
    "agent_tool_call": _APPEND_ONLY,
    "care_event_version": _APPEND_ONLY,
    "deletion_tombstone": _APPEND_ONLY,
    "elder_care_profile_entry": _APPEND_ONLY,
    "elder_enrollment": _APPEND_ONLY,
    "memory_confirmation": _APPEND_ONLY,
    "memory_version": _APPEND_ONLY,
    "report_version": _APPEND_ONLY,
    "review_decision": _APPEND_ONLY,
    "safety_evaluation": _APPEND_ONLY,
    "summary_version": _APPEND_ONLY,
    # Mutable application-owned state.  DELETE remains denied.
    "agent_run": _READ_WRITE,
    "asr_gate_evidence": _READ_WRITE,
    "assisted_elder_session": _READ_WRITE,
    "care_action": _READ_WRITE,
    "care_assignment": _READ_WRITE,
    "care_event": _READ_WRITE,
    "conversation_session": _READ_WRITE,
    "daily_summary": _READ_WRITE,
    "deletion_job_item": _READ_WRITE,
    "deletion_request": _READ_WRITE,
    "family_report": _READ_WRITE,
    "graph_projection_record": _READ_WRITE,
    "memory": _READ_WRITE,
    "notification_delivery": _READ_WRITE,
    "notification_preference": _READ_WRITE,
    # Security/consent/infrastructure state gets INSERT plus column-scoped UPDATE.
    "account_merge_request": _APPEND_ONLY,
    "actor": _APPEND_ONLY,
    "actor_tenant_membership": _APPEND_ONLY,
    "app_session": _APPEND_ONLY,
    "care_relationship": _APPEND_ONLY,
    "consent_grant": _APPEND_ONLY,
    "elder": _APPEND_ONLY,
    "external_identity": _APPEND_ONLY,
    "family_invitation": _APPEND_ONLY,
    "family_relationship": _APPEND_ONLY,
    "kinsun_email_challenge": _APPEND_ONLY,
    "line_link_challenge": _APPEND_ONLY,
    "line_webhook_receipt": _APPEND_ONLY,
    "outbox_event": _APPEND_ONLY,
    "password_credential": _APPEND_ONLY,
    "pending_external_identity": _APPEND_ONLY,
    "tenant": _APPEND_ONLY,
    # Expired idempotency snapshots are the sole runtime-owned physical deletion.
    "idempotency_record": _READ_APPEND_DELETE,
}

# Schemas outside eldercare_ai that hold operational security state rather than
# domain rows.  Each is enumerated table by table for the same reason as above:
# a future table in a shared schema receives no runtime DML until it is listed.
RUNTIME_SHARED_SCHEMA_PRIVILEGES: dict[str, dict[str, tuple[str, ...]]] = {
    # Single-use service credential IDs.  Claims are inserted, never edited, and
    # expired rows are purged by the same runtime role.
    "service_identity": {
        "credential_nonce": _READ_APPEND_DELETE,
        "speech_synthesis_claim": _READ_APPEND_DELETE,
    },
}

PROTECTED_SHARED_TABLE_DENY_MATRIX: dict[str, dict[str, tuple[str, ...]]] = {
    "service_identity": {
        "credential_nonce": ("UPDATE", "TRUNCATE", "REFERENCES", "TRIGGER"),
        "speech_synthesis_claim": ("UPDATE", "TRUNCATE", "REFERENCES", "TRIGGER"),
    },
}

RUNTIME_COLUMN_UPDATE_PRIVILEGES: dict[str, tuple[str, ...]] = {
    "account_merge_request": (
        "status",
        "reason_code",
        "completed_at",
        "version",
        "updated_at",
    ),
    "actor": ("status", "updated_at"),
    "actor_tenant_membership": (
        "status",
        "effective_from",
        "effective_to",
        "updated_at",
    ),
    "app_session": (
        "status",
        "last_seen_at",
        "idle_expires_at",
        "revoked_at",
        "version",
        "updated_at",
    ),
    "care_relationship": (
        "scope",
        "status",
        "effective_from",
        "effective_to",
        "updated_at",
    ),
    "consent_grant": ("status", "revoked_at", "updated_at"),
    "elder": ("status", "updated_at"),
    "external_identity": (
        "status",
        "last_seen_at",
        "encrypted_external_subject",
        "revoked_at",
        "version",
        "updated_at",
    ),
    "family_invitation": (
        "status",
        "attempt_count",
        "redeemed_by_actor_id",
        "redeemed_at",
        "revoked_at",
        "version",
        "updated_at",
    ),
    "family_relationship": (
        "share_scope",
        "status",
        "effective_from",
        "effective_to",
        "updated_at",
    ),
    "idempotency_record": (
        "request_fingerprint",
        "resource_type",
        "resource_id",
        "status",
        "response_status",
        "response_body_hash",
        "response_body",
        "completed_at",
        "expires_at",
    ),
    "kinsun_email_challenge": (
        "status",
        "attempt_count",
        "consumed_at",
        "invalidated_at",
        "version",
        "updated_at",
    ),
    "line_link_challenge": (
        "status",
        "expires_at",
        "attempt_count",
        "redeemed_external_identity_id",
        "redeemed_at",
        "revoked_at",
        "version",
        "updated_at",
    ),
    "line_webhook_receipt": (
        "event_type",
        "status",
        "attempt_count",
        "processed_at",
        "error_code",
        "updated_at",
    ),
    "outbox_event": (
        "delivery_status",
        "published_at",
        "attempt_count",
        "last_error",
        "updated_at",
    ),
    "password_credential": (
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
    ),
    "pending_external_identity": (
        "status",
        "consumed_at",
        "invalidated_at",
        "version",
        "updated_at",
    ),
    "tenant": ("status", "updated_at"),
}

# These assertions are part of the security contract and are also exercised against
# PostgreSQL by the integration suite.
PROTECTED_TABLE_DENY_MATRIX: dict[str, tuple[str, ...]] = {
    "audit_record": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "consent_grant": ("DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"),
    "idempotency_record": ("TRUNCATE", "REFERENCES", "TRIGGER"),
    "outbox_event": ("DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"),
    "policy_registry": ("INSERT", "UPDATE", "DELETE", "TRUNCATE"),
}

PROTECTED_COLUMN_UPDATE_DENY_MATRIX: dict[str, tuple[str, ...]] = {
    "actor": ("actor_type", "display_name", "email", "phone"),
    "actor_tenant_membership": ("actor_id", "tenant_id", "care_unit_id", "role_code"),
    "app_session": ("token_digest", "actor_id", "external_identity_id"),
    "care_relationship": (
        "elder_id",
        "actor_id",
        "tenant_id",
        "care_unit_id",
        "relationship_type",
    ),
    "consent_grant": ("elder_id", "purpose_code", "version", "scope", "policy_id"),
    "elder": ("actor_id", "tenant_id", "primary_care_unit_id", "primary_care_setting"),
    "external_identity": (
        "provider",
        "external_subject_digest",
        "digest_key_version",
        "actor_id",
    ),
    "idempotency_record": (
        "idempotency_key",
        "actor_id",
        "tenant_id",
        "key_format_version",
        "created_at",
    ),
    "family_relationship": ("elder_id", "family_actor_id", "consent_id"),
    "outbox_event": (
        "event_id",
        "event_type",
        "aggregate_type",
        "aggregate_id",
        "tenant_id",
        "payload",
    ),
    "password_credential": (
        "actor_id",
        "algorithm",
    ),
    "tenant": ("tenant_type", "name", "timezone", "default_policy_id"),
}


class RuntimePrincipalConfigurationError(ValueError):
    """Raised when injected runtime credentials violate the staging contract."""


class RuntimePrincipalInvariantError(RuntimeError):
    """Raised when an existing role cannot be reconciled without privilege risk."""


@dataclass(frozen=True)
class RuntimeCredential:
    """Credential material whose representation never includes the password."""

    username: str
    password: str = field(repr=False)


class _PgConnection(Protocol):
    pgconn: Any

    def __enter__(self) -> _PgConnection: ...

    def __exit__(self, *args: object) -> None: ...

    def cursor(self) -> Any: ...


def load_runtime_credential(environ: Mapping[str, str] | None = None) -> RuntimeCredential:
    """Load and validate the separately injected runtime credential.

    The username is deliberately fixed for staging.  Accepting an arbitrary identifier
    from a mutable secret would make a mistaken secret update capable of targeting the
    administrator role.  Password validation errors mention field names only.
    """
    source = os.environ if environ is None else environ
    username = source.get("DB_RUNTIME_USERNAME", "")
    password = source.get("DB_RUNTIME_PASSWORD", "")

    if not username or not _RUNTIME_USERNAME_PATTERN.fullmatch(username):
        raise RuntimePrincipalConfigurationError("DB_RUNTIME_USERNAME is invalid")
    if username != RUNTIME_USERNAME:
        raise RuntimePrincipalConfigurationError("DB_RUNTIME_USERNAME is not the staging role")
    if not 32 <= len(password) <= 1024 or "\x00" in password:
        raise RuntimePrincipalConfigurationError("DB_RUNTIME_PASSWORD is invalid")

    return RuntimeCredential(username=username, password=password)


def _assert_existing_role_is_safe(cursor: Any, username: str) -> None:
    """Reject roles carrying membership or ownership that could imply DDL authority."""
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM pg_auth_members memberships
              JOIN pg_roles members ON members.oid = memberships.member
              JOIN pg_roles granted_roles ON granted_roles.oid = memberships.roleid
             WHERE members.rolname = %s
                OR granted_roles.rolname = %s
        )
        """,
        (username, username),
    )
    if cursor.fetchone()[0]:
        raise RuntimePrincipalInvariantError("runtime role has unexpected role membership")

    cursor.execute(
        """
        WITH runtime_role AS (
            SELECT oid FROM pg_roles WHERE rolname = %s
        )
        SELECT EXISTS (
            SELECT 1 FROM pg_database, runtime_role
             WHERE datname = current_database() AND datdba = runtime_role.oid
            UNION ALL
            SELECT 1 FROM pg_namespace, runtime_role
             WHERE nspowner = runtime_role.oid
            UNION ALL
            SELECT 1 FROM pg_class, runtime_role
             WHERE relowner = runtime_role.oid
            UNION ALL
            SELECT 1 FROM pg_proc, runtime_role
             WHERE proowner = runtime_role.oid
            UNION ALL
            SELECT 1 FROM pg_type, runtime_role
             WHERE typowner = runtime_role.oid
        )
        """,
        (username,),
    )
    if cursor.fetchone()[0]:
        raise RuntimePrincipalInvariantError("runtime role unexpectedly owns database objects")


def _password_verifier(connection: _PgConnection, credential: RuntimeCredential) -> str:
    """Create a SCRAM verifier locally so the cleartext password is never SQL text."""
    verifier = connection.pgconn.encrypt_password(
        credential.password.encode("utf-8"),
        credential.username.encode("utf-8"),
        b"scram-sha-256",
    )
    if not verifier:
        raise RuntimePrincipalInvariantError("could not create runtime password verifier")
    return verifier.decode("ascii")


def _execute_role_reconciliation(
    connection: _PgConnection,
    cursor: Any,
    credential: RuntimeCredential,
    *,
    role_exists: bool,
    admin_username: str,
    database_name: str,
) -> None:
    """Apply role attributes and the reviewed object privileges transactionally."""
    role = sql.Identifier(credential.username)
    schema = sql.Identifier(RUNTIME_SCHEMA)
    database = sql.Identifier(database_name)
    admin = sql.Identifier(admin_username)
    password_verifier = sql.Literal(_password_verifier(connection, credential))

    role_verb = sql.SQL("ALTER ROLE") if role_exists else sql.SQL("CREATE ROLE")
    cursor.execute(
        sql.SQL(
            "{} {} WITH LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS"
        ).format(role_verb, role, password_verifier)
    )
    cursor.execute(
        sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path TO {}, public").format(
            role, database, schema
        )
    )

    # Remove stale explicit privileges before granting the exact runtime set.  PostgreSQL DDL
    # is transactional, so any later failure rolls this entire reconciliation back.
    cursor.execute(sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(database, role))
    cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role))
    cursor.execute(sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA {} FROM {}").format(schema, role))
    cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, role))

    for object_type in ("TABLES", "SEQUENCES", "FUNCTIONS"):
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON ALL {} IN SCHEMA {} FROM {}").format(
                sql.SQL(object_type), schema, role
            )
        )
    cursor.execute(
        """
        SELECT columns.table_name,
               columns.column_name
          FROM information_schema.columns AS columns
         WHERE columns.table_schema = %s
         ORDER BY columns.table_name, columns.ordinal_position
        """,
        (RUNTIME_SCHEMA,),
    )
    columns_by_table: dict[str, list[str]] = {}
    for table_name, column_name in cursor.fetchall():
        columns_by_table.setdefault(table_name, []).append(column_name)
    for table_name, columns in columns_by_table.items():
        column_list = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ({}) ON TABLE {} FROM {}").format(
                column_list,
                sql.Identifier(RUNTIME_SCHEMA, table_name),
                role,
            )
        )
    for table_name, privileges in sorted(RUNTIME_TABLE_PRIVILEGES.items()):
        privilege_list = sql.SQL(", ").join(sql.SQL(privilege) for privilege in privileges)
        cursor.execute(
            sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                privilege_list,
                sql.Identifier(RUNTIME_SCHEMA, table_name),
                role,
            )
        )
    for table_name, columns in sorted(RUNTIME_COLUMN_UPDATE_PRIVILEGES.items()):
        column_list = sql.SQL(", ").join(sql.Identifier(column) for column in columns)
        cursor.execute(
            sql.SQL("GRANT UPDATE ({}) ON TABLE {} TO {}").format(
                column_list,
                sql.Identifier(RUNTIME_SCHEMA, table_name),
                role,
            )
        )

    # Grant sequence access only when a reviewed INSERT-capable table owns that
    # sequence.  UUID-backed tables normally return no rows, but this also handles a
    # future identity/serial column without opening every sequence in the schema.
    insert_tables = sorted(
        table_name
        for table_name, privileges in RUNTIME_TABLE_PRIVILEGES.items()
        if "INSERT" in privileges
    )
    cursor.execute(
        """
        SELECT sequence_namespaces.nspname, sequences.relname
          FROM pg_class AS tables
          JOIN pg_namespace AS table_namespaces
            ON table_namespaces.oid = tables.relnamespace
          JOIN pg_depend AS dependencies
            ON dependencies.refobjid = tables.oid
           AND dependencies.deptype IN ('a', 'i')
          JOIN pg_class AS sequences
            ON sequences.oid = dependencies.objid
           AND sequences.relkind = 'S'
          JOIN pg_namespace AS sequence_namespaces
            ON sequence_namespaces.oid = sequences.relnamespace
         WHERE table_namespaces.nspname = %s
           AND tables.relname = ANY(%s)
         ORDER BY sequence_namespaces.nspname, sequences.relname
        """,
        (RUNTIME_SCHEMA, insert_tables),
    )
    for sequence_schema, sequence_name in cursor.fetchall():
        cursor.execute(
            sql.SQL("GRANT USAGE, SELECT ON SEQUENCE {} TO {}").format(
                sql.Identifier(sequence_schema, sequence_name),
                role,
            )
        )
    # PostgreSQL has no GRANT/REVOKE ``ON ALL TYPES IN SCHEMA`` syntax for existing
    # objects.  Enumerate only user-defined enum/domain types and quote every identifier.
    cursor.execute(
        """
        SELECT types.typname
          FROM pg_type AS types
          JOIN pg_namespace AS namespaces ON namespaces.oid = types.typnamespace
         WHERE namespaces.nspname = %s
           AND types.typtype IN ('d', 'e')
         ORDER BY types.typname
        """,
        (RUNTIME_SCHEMA,),
    )
    for (type_name,) in cursor.fetchall():
        type_identifier = sql.Identifier(RUNTIME_SCHEMA, type_name)
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON TYPE {} FROM {}").format(type_identifier, role)
        )
        cursor.execute(sql.SQL("GRANT USAGE ON TYPE {} TO {}").format(type_identifier, role))

    # Shared operational schemas get USAGE plus an explicit per-table grant.  They
    # deliberately never receive type, sequence or future-object privileges.
    for shared_schema_name, shared_tables in sorted(RUNTIME_SHARED_SCHEMA_PRIVILEGES.items()):
        shared_schema = sql.Identifier(shared_schema_name)
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA {} FROM {}").format(shared_schema, role)
        )
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(shared_schema, role))
        for object_type in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            cursor.execute(
                sql.SQL("REVOKE ALL PRIVILEGES ON ALL {} IN SCHEMA {} FROM {}").format(
                    sql.SQL(object_type), shared_schema, role
                )
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
                    "REVOKE ALL PRIVILEGES ON {} FROM {}"
                ).format(admin, shared_schema, sql.SQL(object_type), role)
            )
        for table_name, privileges in sorted(shared_tables.items()):
            privilege_list = sql.SQL(", ").join(sql.SQL(privilege) for privilege in privileges)
            cursor.execute(
                sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                    privilege_list,
                    sql.Identifier(shared_schema_name, table_name),
                    role,
                )
            )

    for object_type in ("TABLES", "SEQUENCES", "FUNCTIONS", "TYPES"):
        cursor.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
                "REVOKE ALL PRIVILEGES ON {} FROM {}"
            ).format(admin, schema, sql.SQL(object_type), role)
        )
    # Do not grant future tables or sequences automatically.  Each new table must be
    # classified above before the post-migration reconciliation can expose it.
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT USAGE ON TYPES TO {}"
        ).format(admin, schema, role)
    )


def reconcile_runtime_principal(
    admin_database_url: str,
    credential: RuntimeCredential,
    *,
    connect: Callable[[str], _PgConnection] = psycopg.connect,
) -> None:
    """Create/update the runtime LOGIN role after Alembic reaches head.

    The connection is the migration-only administrator connection.  No exception is logged
    here because driver exceptions can contain connection metadata; the outer one-shot job
    emits a fixed error message instead.
    """
    if not admin_database_url.startswith("postgresql+psycopg://"):
        raise RuntimePrincipalConfigurationError("administrator database URL driver is invalid")
    psycopg_dsn = admin_database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    with connect(psycopg_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_PROVISIONING_LOCK_ID,))
            cursor.execute("SELECT current_user, current_database()")
            admin_username, database_name = cursor.fetchone()
            if admin_username == credential.username:
                raise RuntimePrincipalInvariantError(
                    "administrator and runtime roles are identical"
                )

            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)",
                (RUNTIME_SCHEMA,),
            )
            if not cursor.fetchone()[0]:
                raise RuntimePrincipalInvariantError(
                    "runtime schema does not exist after migration"
                )

            for shared_schema_name in sorted(RUNTIME_SHARED_SCHEMA_PRIVILEGES):
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)",
                    (shared_schema_name,),
                )
                if not cursor.fetchone()[0]:
                    raise RuntimePrincipalInvariantError(
                        "shared schema does not exist after migration"
                    )

            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
                (credential.username,),
            )
            role_exists = cursor.fetchone()[0]
            if role_exists:
                _assert_existing_role_is_safe(cursor, credential.username)

            # Disabling statement logging in this transaction is defense in depth: the only
            # password-derived value sent as SQL is a SCRAM verifier, never cleartext.
            cursor.execute("SET LOCAL log_statement = 'none'")
            _execute_role_reconciliation(
                connection,
                cursor,
                credential,
                role_exists=role_exists,
                admin_username=admin_username,
                database_name=database_name,
            )
