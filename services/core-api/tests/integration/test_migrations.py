"""Migration verification tests.

Validates that Alembic migrations can be applied and rolled back cleanly,
ensuring schema changes do not break deployment pipelines.

These tests manage their own database state independently from the
session-scoped migration fixture in conftest.py. Each test starts from
an empty database (the eldercare_ai schema and alembic_version dropped)
and runs upgrade/downgrade sequences manually.

The schema starts from a frozen Alembic baseline (revision f393b4452ce8,
see alembic/versions/20260730_1502_baseline_eldercare_ai_schema_v0_1.py)
that creates the whole `eldercare_ai` schema — 48 tables — in one shot from
a checksummed SQL snapshot. New changes are separate revisions layered on
top; the frozen SQL and expected checksum remain unchanged. Full downgrade
tests intentionally target `base`, then rebuild through every revision.

Validates: Requirements 17.1, 17.2, 17.3, 17.4
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from alembic import command
from alembic.config import Config

# ─── Helpers ─────────────────────────────────────────────────────────────────
#
# `test_engine` here is conftest.py's session-scoped fixture — it uses
# NullPool (see conftest.py), so every checkout is a genuinely fresh
# connection. That matters here specifically: this module runs many
# DROP SCHEMA / CREATE SCHEMA cycles, and a pooled connection reused across
# that much schema churn hits asyncpg connection/prepared-statement-cache
# errors (cached statements or OIDs referring to objects the DDL just
# replaced).

SCHEMA_NAME = "eldercare_ai"
RAG_SCHEMA_NAME = "rag_public"

#: The eight tables that back the identity & elder assignment domain.
#: The baseline creates 48 tables in total (the wider eldercare_ai product
#: schema); these are the ones this module's ORM layer and repositories map
#: onto (see app/models/*.py and the table mapping in AGENTS.md).
_CORE_TABLES = sorted(
    [
        "actor",
        "tenant",
        "care_unit",
        "actor_tenant_membership",
        "elder",
        "care_relationship",
        "care_assignment",
        "outbox_event",
        "password_credential",
    ]
)

#: Total number of tables after upgrading through the current head revision.
_TOTAL_HEAD_TABLE_COUNT = 64

#: The baseline's revision id (see the migration file's Revision ID header).
_BASELINE_REVISION = "f393b4452ce8"
_HEAD_REVISION = "d0e4f6a8b901"


def _get_alembic_config() -> Config:
    """Build an Alembic config pointing to the project's alembic.ini."""
    project_root = os.path.join(os.path.dirname(__file__), "..", "..")
    alembic_cfg = Config(os.path.join(project_root, "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        os.path.join(project_root, "alembic"),
    )
    return alembic_cfg


def _sync_test_database_url() -> str:
    """Async (asyncpg) TEST_DATABASE_URL converted to the sync (psycopg) URL Alembic uses."""
    async_url = os.environ.get("TEST_DATABASE_URL", "")
    return async_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


def _run_alembic_command(command_fn, target: str) -> None:
    """Invoke an Alembic command (upgrade/downgrade) against the TEST database.

    alembic/env.py's run_migrations_online() always builds its own engine from
    the DATABASE_URL environment variable (see alembic/env.py) — it does not
    honor `config.attributes["connection"]`, unlike the more common Alembic
    recipe of injecting a live connection. Since alembic/ must not be edited
    (it is outside tests/), the only way from here to target the test
    database — rather than whatever DATABASE_URL happens to point at (the dev
    database, per this project's documented test-running instructions) — is
    to temporarily point DATABASE_URL at TEST_DATABASE_URL for the duration
    of the call, exactly like conftest.py's session-scoped `run_migrations`
    fixture already does.

    The `connection` argument accepted by callers (via `conn.run_sync(...)`)
    is intentionally unused for the Alembic call itself: env.py ignores it
    and opens its own psycopg connection instead. Plain DDL helpers in this
    module (_drop_all_tables, the introspection helpers) use the passed
    connection directly and are unaffected by this.
    """
    cfg = _get_alembic_config()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _sync_test_database_url()
    try:
        command_fn(cfg, target)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _run_upgrade(connection, target: str = "head") -> None:  # noqa: ARG001 — see _run_alembic_command
    """Run Alembic upgrade to target against the test database."""
    _run_alembic_command(command.upgrade, target)


def _run_downgrade(connection, target: str = "-1") -> None:  # noqa: ARG001 — see _run_alembic_command
    """Run Alembic downgrade to target against the test database."""
    _run_alembic_command(command.downgrade, target)


def _drop_all_tables(connection) -> None:
    """Drop the eldercare_ai schema and alembic_version to start fresh.

    The baseline's downgrade() does exactly this (DROP SCHEMA ... CASCADE),
    but alembic_version lives in `public` (see the migration's downgrade()
    docstring) and is only removed here, not by the migration itself.
    """
    connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE"))
    connection.execute(text(f"DROP SCHEMA IF EXISTS {RAG_SCHEMA_NAME} CASCADE"))
    connection.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))


def _get_alembic_version(connection) -> str | None:
    """Read the current alembic_version from the database."""
    result = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
    row = result.first()
    return row[0] if row else None


def _get_tables(connection) -> list[str]:
    """Get all eldercare_ai tables from information_schema."""
    result = connection.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema ORDER BY table_name"
        ),
        {"schema": SCHEMA_NAME},
    )
    return [row[0] for row in result]


def _get_columns(connection, table_name: str) -> list[str]:
    """Get column names for one current-head table."""
    result = connection.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table_name "
            "ORDER BY ordinal_position"
        ),
        {"schema": SCHEMA_NAME, "table_name": table_name},
    )
    return [row[0] for row in result]


def _get_indexes(connection, table_name: str) -> list[str]:
    """Get index names for a table (excluding primary key indexes)."""
    result = connection.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = :schema AND tablename = :table_name "
            "AND indexname NOT LIKE '%_pkey'"
        ),
        {"schema": SCHEMA_NAME, "table_name": table_name},
    )
    return [row[0] for row in result]


def _get_check_constraints(connection, table_name: str) -> list[str]:
    """Get user-defined CHECK constraint names for a table in eldercare_ai."""
    result = connection.execute(
        text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "JOIN pg_class rel ON rel.oid = c.conrelid "
            "WHERE n.nspname = :schema AND rel.relname = :table_name AND c.contype = 'c' "
            "ORDER BY c.conname"
        ),
        {"schema": SCHEMA_NAME, "table_name": table_name},
    )
    return [row[0] for row in result]


def _get_unique_constraints(connection, table_name: str) -> list[str]:
    """Get UNIQUE table-constraint names for a table in eldercare_ai.

    Note this only returns constraints created via `UNIQUE (...)`, not
    stand-alone `CREATE UNIQUE INDEX` (e.g. uq_actor_email, uq_membership_scope
    are unique indexes, not table constraints, and show up in _get_indexes
    instead).
    """
    result = connection.execute(
        text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "JOIN pg_class rel ON rel.oid = c.conrelid "
            "WHERE n.nspname = :schema AND rel.relname = :table_name AND c.contype = 'u' "
            "ORDER BY c.conname"
        ),
        {"schema": SCHEMA_NAME, "table_name": table_name},
    )
    return [row[0] for row in result]


def _get_foreign_keys(connection, table_name: str) -> list[str]:
    """Get foreign key constraint names for a table in eldercare_ai."""
    result = connection.execute(
        text(
            "SELECT c.conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "JOIN pg_class rel ON rel.oid = c.conrelid "
            "WHERE n.nspname = :schema AND rel.relname = :table_name AND c.contype = 'f' "
            "ORDER BY c.conname"
        ),
        {"schema": SCHEMA_NAME, "table_name": table_name},
    )
    return [row[0] for row in result]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _restore_schema_after_module(test_engine):
    """Guarantee the schema is back at head once this module's tests finish.

    Tests in this module intentionally drop and rebuild the eldercare_ai
    schema to exercise Alembic upgrade/downgrade paths. `test_engine` is
    session-scoped and shared with every other integration test module, so
    ending this module with the schema absent (e.g. after
    test_baseline_full_downgrade_to_base) would break every test that runs
    afterwards in the same session. This re-applies `alembic upgrade head`
    once, after the last test in this module, regardless of which one ran
    last.
    """
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")


# ─── Tests: Upgrade / Downgrade Lifecycle ────────────────────────────────────


@pytest.mark.asyncio
async def test_upgrade_from_empty_to_head(test_engine):
    """Verify Alembic upgrade from an empty database to head succeeds.

    Validates: Requirement 17.1
    """
    async with test_engine.begin() as conn:
        # Start with a clean slate
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        # Run upgrade from empty to head
        await conn.run_sync(_run_upgrade, "head")

    # Verify alembic_version is set to the baseline revision
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert (
            version == _HEAD_REVISION
        ), f"Expected head revision '{_HEAD_REVISION}', got '{version}'"

    # Verify the outbox_event table exists
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = 'outbox_event'"
            ),
            {"schema": SCHEMA_NAME},
        )
        tables = [row[0] for row in result]
        assert "outbox_event" in tables, "outbox_event table should exist after upgrade"

        tombstone_result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = 'deletion_tombstone'"
            ),
            {"schema": SCHEMA_NAME},
        )
        assert tombstone_result.scalar_one_or_none() == "deletion_tombstone"


@pytest.mark.asyncio
async def test_idempotency_hardening_schema_supports_snapshot_expiry_and_cleanup(
    test_engine,
) -> None:
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        columns = await conn.run_sync(_get_columns, "idempotency_record")
        checks = await conn.run_sync(_get_check_constraints, "idempotency_record")
        indexes = await conn.run_sync(_get_indexes, "idempotency_record")
        delete_rule = await conn.scalar(
            text(
                "SELECT rc.delete_rule FROM information_schema.referential_constraints rc "
                "WHERE rc.constraint_schema = :schema "
                "AND rc.constraint_name = 'agent_tool_call_idempotency_key_fkey'"
            ),
            {"schema": SCHEMA_NAME},
        )

    assert {"response_body", "key_format_version", "completed_at"} <= set(columns)
    assert "ck_idempotency_key_format_version" in checks
    assert "idx_idempotency_record_expiry" in indexes
    assert delete_rule == "SET NULL"


@pytest.mark.asyncio
async def test_dead_letter_status_migration_roundtrip(test_engine):
    """Verify terminal status values and downgrade conversion at the data level."""
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        event_id = await conn.scalar(
            text(
                "INSERT INTO eldercare_ai.outbox_event "
                "(event_id, event_type, aggregate_type, aggregate_id, "
                "aggregate_version, trace_id, payload, delivery_status, "
                "attempt_count, last_error) "
                "VALUES (gen_random_uuid(), 'migration.smoke.v1', 'memory', "
                "gen_random_uuid(), 1, 'trace-migration', '{}'::jsonb, "
                "'DEAD_LETTER', 3, 'PUBLISHER_ATTEMPT_LIMIT_REACHED') "
                "RETURNING event_id"
            )
        )

    with pytest.raises(IntegrityError):
        async with test_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE eldercare_ai.outbox_event "
                    "SET delivery_status = 'UNSUPPORTED' WHERE event_id = :event_id"
                ),
                {"event_id": event_id},
            )

    async with test_engine.begin() as conn:
        # Newer migrations now sit above the dead-letter migration. Target its
        # direct parent so this test still exercises the e4 downgrade itself.
        await conn.run_sync(_run_downgrade, "d3b7e2a4f901")

    async with test_engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT delivery_status, last_error "
                    "FROM eldercare_ai.outbox_event WHERE event_id = :event_id"
                ),
                {"event_id": event_id},
            )
        ).one()
        assert row.delivery_status == "FAILED"
        assert row.last_error == "PUBLISHER_ATTEMPT_LIMIT_REACHED"

    with pytest.raises(IntegrityError):
        async with test_engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE eldercare_ai.outbox_event "
                    "SET delivery_status = 'DEAD_LETTER' WHERE event_id = :event_id"
                ),
                {"event_id": event_id},
            )

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")


@pytest.mark.asyncio
async def test_downgrade_from_head_removes_schema(test_engine):
    """Verify Alembic downgrade from head to base removes the schema.

    Validates: Requirement 17.2
    """
    # Start fresh and upgrade to head
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Downgrade through every revision to the empty base.
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_downgrade, "base")

    # Verify alembic_version is now empty (no revisions applied)
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert version is None, f"Expected no version after downgrade, got '{version}'"

    # Verify the eldercare_ai schema itself is gone
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
            {"schema": SCHEMA_NAME},
        )
        assert result.first() is None, "eldercare_ai schema should not exist after downgrade"


@pytest.mark.asyncio
async def test_upgrade_downgrade_upgrade_roundtrip(test_engine):
    """Verify upgrade -> downgrade -> upgrade produces same state as single upgrade.

    Validates: Requirement 17.3
    """
    # Start fresh and do a single upgrade to head to get reference state
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Capture the reference alembic_version after single upgrade
    async with test_engine.begin() as conn:
        reference_version = await conn.run_sync(_get_alembic_version)

    # Now drop everything and do the round-trip: upgrade -> downgrade -> upgrade
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_downgrade, "-1")

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Verify the alembic_version matches the reference
    async with test_engine.begin() as conn:
        roundtrip_version = await conn.run_sync(_get_alembic_version)

    assert roundtrip_version == reference_version, (
        f"Round-trip version '{roundtrip_version}' does not match "
        f"reference version '{reference_version}'"
    )

    # Verify the outbox_event table exists (schema is consistent)
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = 'outbox_event'"
            ),
            {"schema": SCHEMA_NAME},
        )
        tables = [row[0] for row in result]
        assert (
            "outbox_event" in tables
        ), "outbox_event table should exist after round-trip migration"


# ─── Tests: Baseline Schema Objects (identity & elder assignment tables) ─────


@pytest.mark.asyncio
async def test_head_upgrade_creates_expected_tables(test_engine):
    """Verify all migrations through head create expected tables, including the core 8.

    Validates: Requirement 16.1, 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        tables = await conn.run_sync(_get_tables)

    assert len(tables) == _TOTAL_HEAD_TABLE_COUNT, (
        f"Expected {_TOTAL_HEAD_TABLE_COUNT} tables in eldercare_ai, "
        f"got {len(tables)}: {tables}"
    )
    missing = set(_CORE_TABLES) - set(tables)
    assert not missing, f"Expected core tables {_CORE_TABLES} to be a subset, missing: {missing}"
    assert "decision_support_profile" in tables
    assert {
        "elder_enrollment",
        "elder_care_profile_entry",
        "assisted_elder_session",
    } <= set(tables)


@pytest.mark.asyncio
async def test_public_rag_projection_migration_isolated_and_vector_ready(test_engine) -> None:
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        extensions = {
            row.extname: (row.extversion, row.schema_name)
            for row in (
                await conn.execute(
                    text(
                        "SELECT e.extname, e.extversion, n.nspname AS schema_name "
                        "FROM pg_extension e "
                        "JOIN pg_namespace n ON n.oid = e.extnamespace "
                        "WHERE extname IN ('vector', 'pg_trgm')"
                    )
                )
            )
        }
        rag_tables = {
            row.table_name
            for row in (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = :schema"
                    ),
                    {"schema": RAG_SCHEMA_NAME},
                )
            )
        }
        vector_type = await conn.scalar(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema "
                "AND c.relname = 'chunk_embedding' "
                "AND a.attname = 'embedding'"
            ),
            {"schema": RAG_SCHEMA_NAME},
        )
        public_grant_count = await conn.scalar(
            text(
                "SELECT count(*) FROM information_schema.role_table_grants "
                "WHERE table_schema = :schema AND grantee = 'PUBLIC'"
            ),
            {"schema": RAG_SCHEMA_NAME},
        )
        indexes = {
            row.indexname
            for row in (
                await conn.execute(
                    text("SELECT indexname FROM pg_indexes " "WHERE schemaname = :schema"),
                    {"schema": RAG_SCHEMA_NAME},
                )
            )
        }

    assert set(extensions) == {"pg_trgm", "vector"}
    assert {schema_name for _, schema_name in extensions.values()} == {"public"}
    assert rag_tables == {
        "chunk_embedding",
        "chunk_projection",
        "embedding_profile",
        "ingestion_run",
        "rag_release",
    }
    assert vector_type == "vector(1024)"
    assert public_grant_count == 0
    assert {
        "ix_rag_chunk_embedding_hnsw",
        "ix_rag_chunk_lexical_trgm",
        "ix_rag_chunk_search_vector",
    }.issubset(indexes)


@pytest.mark.asyncio
async def test_public_rag_release_rejects_incompatible_embedding_profile(test_engine) -> None:
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    # Alembic opens its own synchronous connection. Run it after the schema
    # cleanup transaction commits so the two connections cannot deadlock on
    # alembic_version.
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO rag_public.embedding_profile "
                "(embedding_profile_id, provider, model_id, dimension, "
                "document_task_type, config_version) VALUES "
                "('google-v1', 'google', 'gemini-embedding-001', 1024, "
                "'RETRIEVAL_DOCUMENT', 'v1'), "
                "('other-v1', 'other', 'other-embedding', 1024, "
                "'RETRIEVAL_DOCUMENT', 'v1')"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO rag_public.rag_release "
                "(release_id, artifact_version, candidate_sha256, source_count, "
                "chunk_count, release_status, review_status, human_source_review, "
                "production_approved, embedding_profile_id) VALUES "
                "('test-v1', 'v001', :digest, 1, 1, 'APPROVED', 'reviewed', "
                "'COMPLETED', true, 'google-v1')"
            ),
            {"digest": "a" * 64},
        )
        await conn.execute(
            text(
                "INSERT INTO rag_public.chunk_projection "
                "(release_id, chunk_id, source_id, chunk_index, artifact_version, "
                "schema_version, document_title, content_type, language, locale, "
                "chunk_text, embedding_text, text_sha256, embedding_text_sha256, "
                "record_sha256, review_status, current_status, risk_level, production_approved, "
                "retrieval_eligible, citation, governance, provenance, retrieval_policy) "
                "VALUES ('test-v1', 'chunk-1', 'source-1', 1, 'v001', '2.1.0', "
                "'title', 'guide', 'zh-Hant', 'zh-TW', 'text', 'embedding text', "
                ":text_digest, :embedding_digest, :record_digest, 'reviewed', 'current', 'low', "
                "true, true, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb)"
            ),
            {
                "text_digest": "b" * 64,
                "embedding_digest": "c" * 64,
                "record_digest": "d" * 64,
            },
        )

    with pytest.raises(IntegrityError):
        async with test_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO rag_public.chunk_embedding "
                    "(release_id, chunk_id, embedding_profile_id, "
                    "embedding_text_sha256, embedding) VALUES "
                    "('test-v1', 'chunk-1', 'other-v1', :digest, "
                    "('[' || array_to_string(array_fill(0.0::float8, ARRAY[1024]), ',') "
                    "|| ']')::vector)"
                ),
                {"digest": "c" * 64},
            )


@pytest.mark.asyncio
async def test_decision_support_profile_migration_binds_memory_evidence(test_engine) -> None:
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        profile_columns = await conn.run_sync(_get_columns, "decision_support_profile")
        memory_columns = await conn.run_sync(_get_columns, "memory")
        profile_checks = await conn.run_sync(
            _get_check_constraints,
            "decision_support_profile",
        )
        profile_fks = await conn.run_sync(_get_foreign_keys, "decision_support_profile")
        memory_fks = await conn.run_sync(_get_foreign_keys, "memory")
        confirmation_fks = await conn.run_sync(_get_foreign_keys, "memory_confirmation")

    assert {
        "decision_support_profile_id",
        "tenant_id",
        "elder_id",
        "decision_scope",
        "data_class",
        "mode",
        "allowed_memory_risks",
        "basis_reference",
        "effective_from",
        "expires_at",
        "reviewed_by_actor_id",
        "policy_version",
        "profile_version",
        "supersedes_profile_id",
    } <= set(profile_columns)
    assert {
        "decision_support_profile_id",
        "decision_support_profile_version",
    } <= set(memory_columns)
    assert "ck_decision_support_profile_mode" in profile_checks
    assert "ck_decision_support_profile_allowed_risks" in profile_checks
    assert "fk_decision_support_profile_tenant" in profile_fks
    assert "fk_decision_support_profile_elder" in profile_fks
    assert "fk_memory_decision_support_profile" in memory_fks
    assert "fk_memory_confirmation_decision_support_profile" in confirmation_fks


@pytest.mark.asyncio
async def test_memory_confirmation_rows_are_append_only(test_engine) -> None:
    confirmation_id = "92000000-0000-4000-8000-000000000001"
    seed_sql = """
        INSERT INTO eldercare_ai.tenant
            (tenant_id, tenant_type, name, status, timezone)
        VALUES
            ('92000000-0000-4000-8000-000000000010', 'DEMO',
             'Append-only test tenant', 'ACTIVE', 'UTC');

        INSERT INTO eldercare_ai.actor
            (actor_id, actor_type, display_name, status)
        VALUES
            ('92000000-0000-4000-8000-000000000011', 'ELDER',
             'Append-only test elder actor', 'ACTIVE');

        INSERT INTO eldercare_ai.elder
            (elder_id, tenant_id, actor_id, display_name,
             primary_care_setting, status, preferred_language,
             response_length_preference, timezone)
        VALUES
            ('92000000-0000-4000-8000-000000000012',
             '92000000-0000-4000-8000-000000000010',
             '92000000-0000-4000-8000-000000000011',
             'Append-only test elder', 'INDEPENDENT', 'ACTIVE',
             'ZH_TW', 'STANDARD', 'UTC');

        INSERT INTO eldercare_ai.policy_registry
            (policy_id, owner_tenant_id, policy_code, policy_type,
             version, status, policy_payload, effective_from)
        VALUES
            ('92000000-0000-4000-8000-000000000013',
             '92000000-0000-4000-8000-000000000010',
             'append-only-memory-consent', 'CONSENT', '1',
             'ACTIVE', '{}'::jsonb, '2026-01-01T00:00:00Z');

        INSERT INTO eldercare_ai.consent_grant
            (consent_id, elder_id, purpose_code, status, version, scope,
             granted_by_actor_id, policy_id, granted_at, effective_at)
        VALUES
            ('92000000-0000-4000-8000-000000000014',
             '92000000-0000-4000-8000-000000000012',
             'LONG_TERM_MEMORY', 'GRANTED', 1, '{}'::jsonb,
             '92000000-0000-4000-8000-000000000011',
             '92000000-0000-4000-8000-000000000013',
             '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');

        INSERT INTO eldercare_ai.memory
            (memory_id, elder_id, tenant_id, memory_type, status,
             current_version, consent_id, consent_version, evidence_state)
        VALUES
            ('92000000-0000-4000-8000-000000000003',
             '92000000-0000-4000-8000-000000000012',
             '92000000-0000-4000-8000-000000000010',
             'ROUTINE', 'PENDING_CONFIRMATION', 1,
             '92000000-0000-4000-8000-000000000014', 1, 'CURRENT');

        INSERT INTO eldercare_ai.memory_confirmation
            (memory_confirmation_id, tenant_id, elder_id, memory_id,
             memory_version, content_digest, consent_id, consent_version,
             policy_version, confirmation_method, response_intent,
             confirmed_by_actor_id, speaker_verification_level,
             speaker_evidence_reference, confirmation_evidence_reference,
             trace_id, idempotency_key, confirmed_at)
        VALUES
            (:confirmation_id,
             '92000000-0000-4000-8000-000000000010',
             '92000000-0000-4000-8000-000000000012',
             '92000000-0000-4000-8000-000000000003',
             1, :content_digest,
             '92000000-0000-4000-8000-000000000014', 1,
             'memory-policy-2026-08-18.v1', 'ELDER_UI', 'AFFIRM',
             '92000000-0000-4000-8000-000000000011', 'VERIFIED_ELDER',
             'speaker-evidence:append-only-test',
             'core-command:append-only-test',
             'trace-append-only-test', 'append-only-test:1', now());
    """
    seed_params = {
        "confirmation_id": confirmation_id,
        "content_digest": "a" * 64,
    }

    async with test_engine.connect() as conn:
        transaction = await conn.begin()
        try:
            for statement in seed_sql.split(";"):
                if statement.strip():
                    await conn.execute(text(statement), seed_params)

            with pytest.raises(DBAPIError, match="append-only"):
                async with conn.begin_nested():
                    await conn.execute(
                        text(
                            "UPDATE eldercare_ai.memory_confirmation "
                            "SET trace_id = 'tampered' "
                            "WHERE memory_confirmation_id = :confirmation_id"
                        ),
                        {"confirmation_id": confirmation_id},
                    )

            with pytest.raises(DBAPIError, match="append-only"):
                async with conn.begin_nested():
                    await conn.execute(
                        text(
                            "DELETE FROM eldercare_ai.memory_confirmation "
                            "WHERE memory_confirmation_id = :confirmation_id"
                        ),
                        {"confirmation_id": confirmation_id},
                    )

            remaining = await conn.scalar(
                text(
                    "SELECT count(*) FROM eldercare_ai.memory_confirmation "
                    "WHERE memory_confirmation_id = :confirmation_id"
                ),
                {"confirmation_id": confirmation_id},
            )
            assert remaining == 1
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
async def test_legacy_memory_backfill_quarantines_and_survives_downgrade(test_engine) -> None:
    previous_head = "a4c6e8f0b123"
    active_memory_id = "91000000-0000-4000-8000-000000000001"
    pending_memory_id = "91000000-0000-4000-8000-000000000002"
    current_memory_id = "91000000-0000-4000-8000-000000000003"

    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, previous_head)

    async with test_engine.begin() as conn:
        seed_sql = """
                INSERT INTO eldercare_ai.tenant
                    (tenant_id, tenant_type, name, status, timezone)
                VALUES
                    ('91000000-0000-4000-8000-000000000010', 'DEMO',
                     'Synthetic legacy tenant', 'ACTIVE', 'Asia/Taipei');

                INSERT INTO eldercare_ai.actor
                    (actor_id, actor_type, display_name, status)
                VALUES
                    ('91000000-0000-4000-8000-000000000011', 'ELDER',
                     'Synthetic legacy elder actor', 'ACTIVE');

                INSERT INTO eldercare_ai.elder
                    (elder_id, tenant_id, actor_id, display_name,
                     primary_care_setting, status, preferred_language,
                     response_length_preference, timezone)
                VALUES
                    ('91000000-0000-4000-8000-000000000012',
                     '91000000-0000-4000-8000-000000000010',
                     '91000000-0000-4000-8000-000000000011',
                     'Synthetic legacy elder', 'INDEPENDENT', 'ACTIVE',
                     'ZH_TW', 'STANDARD', 'Asia/Taipei');

                INSERT INTO eldercare_ai.policy_registry
                    (policy_id, owner_tenant_id, policy_code, policy_type,
                     version, status, policy_payload, effective_from)
                VALUES
                    ('91000000-0000-4000-8000-000000000013',
                     '91000000-0000-4000-8000-000000000010',
                     'synthetic-legacy-memory-consent', 'CONSENT', '1',
                     'ACTIVE', '{}'::jsonb, '2026-01-01T00:00:00Z');

                INSERT INTO eldercare_ai.consent_grant
                    (consent_id, elder_id, purpose_code, status, version, scope,
                     granted_by_actor_id, policy_id, granted_at, effective_at)
                VALUES
                    ('91000000-0000-4000-8000-000000000014',
                     '91000000-0000-4000-8000-000000000012',
                     'LONG_TERM_MEMORY', 'GRANTED', 1, '{}'::jsonb,
                     '91000000-0000-4000-8000-000000000011',
                     '91000000-0000-4000-8000-000000000013',
                     '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');

                INSERT INTO eldercare_ai.care_event
                    (event_id, elder_id, tenant_id, event_type, status,
                     current_version, consent_version)
                VALUES
                    ('91000000-0000-4000-8000-000000000015',
                     '91000000-0000-4000-8000-000000000012',
                     '91000000-0000-4000-8000-000000000010',
                     'PERSONAL_PREFERENCE', 'VERIFIED', 1, 1);

                INSERT INTO eldercare_ai.care_event_version
                    (event_id, version, structured_payload,
                     memory_candidate_proposal, speaker_role,
                     speaker_actor_id, speaker_verification_level,
                     speaker_verification_method, speaker_evidence_reference,
                     created_by_actor_id)
                VALUES
                    ('91000000-0000-4000-8000-000000000015', 1, '{}'::jsonb,
                     jsonb_build_object(
                       'memory_type', 'PERSONAL_HISTORY',
                       'memory_kind', 'FAMILY_RELATIONSHIP',
                       'normalized_content', 'Synthetic current pending content',
                       'confirmation_question', 'Remember this synthetic item?',
                       'extraction_confidence', 0.9,
                       'proposal_risk_hint', 'MEDIUM',
                       'extractor_version', 'synthetic-extractor-v1'
                     ),
                     'ELDER', '91000000-0000-4000-8000-000000000011',
                     'VERIFIED_ELDER', 'AUTHENTICATED_TEXT',
                     'speaker-evidence:synthetic-current',
                     '91000000-0000-4000-8000-000000000011');

                INSERT INTO eldercare_ai.memory
                    (memory_id, elder_id, tenant_id, memory_type, memory_kind,
                     actual_risk_level, policy_decision, policy_version,
                     verification_level, required_verification,
                     speaker_verification_level, speaker_evidence_reference,
                     status, current_version, consent_id, consent_version)
                VALUES
                    (:active_memory_id,
                     '91000000-0000-4000-8000-000000000012',
                     '91000000-0000-4000-8000-000000000010',
                     'PREFERENCE', NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                     NULL, 'ACTIVE', 1, NULL, 1),
                    (:pending_memory_id,
                     '91000000-0000-4000-8000-000000000012',
                     '91000000-0000-4000-8000-000000000010',
                     'ROUTINE', NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                     NULL, 'PENDING_CONFIRMATION', 1, NULL, 1),
                    (:current_memory_id,
                     '91000000-0000-4000-8000-000000000012',
                     '91000000-0000-4000-8000-000000000010',
                     'PERSONAL_HISTORY', 'FAMILY_RELATIONSHIP', 'MEDIUM',
                     'PENDING_ELDER_CONFIRMATION',
                     'memory-policy-2026-08-18.v1', 'UNVERIFIED',
                     'ELDER_CONFIRMATION', 'VERIFIED_ELDER',
                     'speaker-evidence:synthetic-current',
                     'PENDING_CONFIRMATION', 1,
                     '91000000-0000-4000-8000-000000000014', 1);

                INSERT INTO eldercare_ai.memory_version
                    (memory_id, version, content, content_digest,
                     confirmation_question, extractor_version,
                     extraction_confidence, source_event_ids,
                     source_turn_reference, proposal_risk_hint, version_status)
                VALUES
                    (:active_memory_id, 1, 'Synthetic legacy active content',
                     NULL, NULL, NULL, NULL, '{}', NULL, NULL, 'ACTIVE'),
                    (:pending_memory_id, 1, 'Synthetic legacy pending content',
                     NULL, NULL, NULL, NULL, '{}', NULL, NULL, 'ACTIVE'),
                    (:current_memory_id, 1, 'Synthetic current pending content',
                     encode(digest(convert_to(
                       'Synthetic current pending content', 'UTF8'
                     ), 'sha256'), 'hex'),
                     'Remember this synthetic item?', 'synthetic-extractor-v1',
                     0.9,
                     ARRAY['91000000-0000-4000-8000-000000000015'::uuid],
                     'care-event:91000000-0000-4000-8000-000000000015:v1',
                     'MEDIUM', 'ACTIVE');
                """
        seed_params = {
            "active_memory_id": active_memory_id,
            "pending_memory_id": pending_memory_id,
            "current_memory_id": current_memory_id,
        }
        for statement in seed_sql.split(";"):
            if statement.strip():
                await conn.execute(text(statement), seed_params)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    async with test_engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT memory_id::text, evidence_state, status, "
                    "lifecycle_reason, deactivated_at IS NOT NULL "
                    "FROM eldercare_ai.memory ORDER BY memory_id"
                )
            )
        ).all()
        columns = await conn.run_sync(_get_columns, "memory")
        checks = await conn.run_sync(_get_check_constraints, "memory")
        indexes = await conn.run_sync(_get_indexes, "memory")

    assert rows == [
        (
            active_memory_id,
            "LEGACY_NEEDS_REVIEW",
            "INACTIVE",
            "LEGACY_NEEDS_REVIEW",
            True,
        ),
        (
            pending_memory_id,
            "LEGACY_NEEDS_REVIEW",
            "DEFERRED",
            "LEGACY_NEEDS_REVIEW",
            False,
        ),
        (
            current_memory_id,
            "CURRENT",
            "PENDING_CONFIRMATION",
            None,
            False,
        ),
    ]
    assert "evidence_state" in columns
    assert "ck_memory_evidence_state" in checks
    assert "ck_memory_legacy_not_active" in checks
    assert "ix_memory_evidence_context" in indexes

    async with test_engine.begin() as conn:
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(
                    text(
                        "UPDATE eldercare_ai.memory SET status = 'ACTIVE' "
                        "WHERE memory_id = :memory_id"
                    ),
                    {"memory_id": active_memory_id},
                )

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_downgrade, previous_head)

    async with test_engine.begin() as conn:
        columns_after_downgrade = await conn.run_sync(_get_columns, "memory")
        statuses_after_downgrade = (
            await conn.execute(
                text(
                    "SELECT memory_id::text, status FROM eldercare_ai.memory " "ORDER BY memory_id"
                )
            )
        ).all()

    assert "evidence_state" not in columns_after_downgrade
    assert statuses_after_downgrade == [
        (active_memory_id, "INACTIVE"),
        (pending_memory_id, "DEFERRED"),
        (current_memory_id, "PENDING_CONFIRMATION"),
    ]

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")


@pytest.mark.asyncio
async def test_baseline_upgrade_creates_all_indexes(test_engine):
    """Verify the baseline migration creates all expected composite indexes
    on the identity & elder assignment tables.

    Validates: Requirement 16.2, 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    expected_indexes = [
        "idx_actor_status",
        "uq_actor_email",
        "idx_membership_actor_active",
        "uq_membership_scope",
        "idx_elder_tenant_unit",
        "idx_relationship_elder_actor",
        "idx_assignment_worker_time",
        "idx_assignment_elder_time",
        "idx_outbox_pending",
        "uq_care_unit_name",
        "outbox_event_event_id_key",
    ]

    async with test_engine.begin() as conn:
        all_indexes: list[str] = []
        for table in _CORE_TABLES:
            indexes = await conn.run_sync(_get_indexes, table)
            all_indexes.extend(indexes)

    for idx in expected_indexes:
        assert idx in all_indexes, f"Expected index '{idx}' not found. Found: {all_indexes}"


@pytest.mark.asyncio
async def test_baseline_upgrade_creates_check_constraints(test_engine):
    """Verify the baseline migration creates all expected CHECK constraints
    on the identity & elder assignment tables.

    Validates: Requirement 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    expected_checks = [
        "actor_status_check",
        "actor_tenant_membership_status_check",
        "ck_membership_period",
        "care_unit_status_check",
        "elder_primary_care_setting_check",
        "elder_response_length_preference_check",
        "elder_status_check",
        "care_relationship_status_check",
        "ck_care_relationship_period",
        "care_assignment_status_check",
        "care_assignment_version_check",
        "ck_assignment_period",
        "tenant_status_check",
        "outbox_event_aggregate_version_check",
        "outbox_event_attempt_count_check",
        "outbox_event_delivery_status_check",
    ]

    async with test_engine.begin() as conn:
        all_checks: list[str] = []
        for table in _CORE_TABLES:
            checks = await conn.run_sync(_get_check_constraints, table)
            all_checks.extend(checks)

    for chk in expected_checks:
        assert (
            chk in all_checks
        ), f"Expected CHECK constraint '{chk}' not found. Found: {all_checks}"


@pytest.mark.asyncio
async def test_head_upgrade_creates_expected_unique_constraints(test_engine):
    """Verify current head has only the expected UNIQUE constraints.

    Note: uq_actor_email and uq_membership_scope are stand-alone unique
    indexes (see test_baseline_upgrade_creates_all_indexes), not table
    constraints, so they are intentionally not asserted here. The retired
    Cognito subject column and its table constraint must not survive at head.

    Validates: Requirement 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    expected_unique = [
        "uq_care_unit_name",
        "outbox_event_event_id_key",
    ]

    async with test_engine.begin() as conn:
        all_unique: list[str] = []
        for table in _CORE_TABLES:
            unique_constraints = await conn.run_sync(_get_unique_constraints, table)
            all_unique.extend(unique_constraints)

    for uq in expected_unique:
        assert uq in all_unique, f"Expected UNIQUE constraint '{uq}' not found. Found: {all_unique}"

    assert "uq_actor_cognito_sub" not in all_unique
    async with test_engine.begin() as conn:
        actor_columns = await conn.run_sync(_get_columns, "actor")
    assert "cognito_sub" not in actor_columns


@pytest.mark.asyncio
async def test_baseline_upgrade_creates_foreign_keys(test_engine):
    """Verify the baseline migration creates all expected foreign key
    constraints on the identity & elder assignment tables.

    Validates: Requirement 16.3, 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    expected_fks = [
        "care_unit_tenant_id_fkey",
        "actor_tenant_membership_actor_id_fkey",
        "actor_tenant_membership_care_unit_id_fkey",
        "actor_tenant_membership_tenant_id_fkey",
        "elder_tenant_id_fkey",
        "elder_primary_care_unit_id_fkey",
        "care_relationship_elder_id_fkey",
        "care_relationship_actor_id_fkey",
        "care_relationship_tenant_id_fkey",
        "care_relationship_care_unit_id_fkey",
        "care_assignment_tenant_id_fkey",
        "care_assignment_care_unit_id_fkey",
        "care_assignment_elder_id_fkey",
        "care_assignment_worker_actor_id_fkey",
        "outbox_event_tenant_id_fkey",
        "outbox_event_elder_id_fkey",
        "outbox_event_actor_id_fkey",
    ]

    async with test_engine.begin() as conn:
        all_fks: list[str] = []
        for table in _CORE_TABLES:
            fks = await conn.run_sync(_get_foreign_keys, table)
            all_fks.extend(fks)

    for fk in expected_fks:
        assert fk in all_fks, f"Expected FK constraint '{fk}' not found. Found: {all_fks}"


@pytest.mark.asyncio
async def test_baseline_roundtrip_upgrade_downgrade_upgrade(test_engine):
    """Verify baseline migration upgrade -> downgrade -> upgrade completes cleanly
    and restores all schema objects for the identity & elder assignment tables.

    Validates: Requirement 16.5, 16.6
    """
    # Start fresh
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    # Upgrade to head
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Verify we're at the baseline revision
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert version == _HEAD_REVISION

    # Downgrade through every revision to base (drops the whole schema).
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_downgrade, "base")

    # Verify the schema is gone
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
            {"schema": SCHEMA_NAME},
        )
        assert result.first() is None, "eldercare_ai schema should not exist after downgrade"

    # Verify version is empty
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert version is None

    # Upgrade back to head
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Verify we're back at the baseline revision
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert version == _HEAD_REVISION

    # Verify all current-head tables (including our core 8) are restored.
    async with test_engine.begin() as conn:
        tables = await conn.run_sync(_get_tables)
    assert len(tables) == _TOTAL_HEAD_TABLE_COUNT
    assert set(_CORE_TABLES) <= set(tables)

    # Verify all indexes are restored
    expected_indexes = [
        "idx_actor_status",
        "uq_actor_email",
        "idx_membership_actor_active",
        "uq_membership_scope",
        "idx_elder_tenant_unit",
        "idx_relationship_elder_actor",
        "idx_assignment_worker_time",
        "idx_assignment_elder_time",
        "idx_outbox_pending",
        "uq_care_unit_name",
        "outbox_event_event_id_key",
    ]

    async with test_engine.begin() as conn:
        all_indexes: list[str] = []
        for table in _CORE_TABLES:
            indexes = await conn.run_sync(_get_indexes, table)
            all_indexes.extend(indexes)

    for idx in expected_indexes:
        assert (
            idx in all_indexes
        ), f"Expected index '{idx}' not restored after round-trip. Found: {all_indexes}"

    # Verify all check constraints are restored
    expected_checks = [
        "actor_status_check",
        "ck_membership_period",
        "care_unit_status_check",
        "elder_status_check",
        "ck_care_relationship_period",
        "ck_assignment_period",
        "tenant_status_check",
    ]

    async with test_engine.begin() as conn:
        all_checks: list[str] = []
        for table in _CORE_TABLES:
            checks = await conn.run_sync(_get_check_constraints, table)
            all_checks.extend(checks)

    for chk in expected_checks:
        assert (
            chk in all_checks
        ), f"Expected CHECK constraint '{chk}' not restored after round-trip. Found: {all_checks}"

    # Verify all foreign keys are restored
    expected_fks = [
        "care_unit_tenant_id_fkey",
        "actor_tenant_membership_actor_id_fkey",
        "actor_tenant_membership_care_unit_id_fkey",
        "actor_tenant_membership_tenant_id_fkey",
        "elder_tenant_id_fkey",
        "elder_primary_care_unit_id_fkey",
        "care_relationship_elder_id_fkey",
        "care_relationship_actor_id_fkey",
        "care_relationship_tenant_id_fkey",
        "care_relationship_care_unit_id_fkey",
        "care_assignment_tenant_id_fkey",
        "care_assignment_care_unit_id_fkey",
        "care_assignment_elder_id_fkey",
        "care_assignment_worker_actor_id_fkey",
        "outbox_event_tenant_id_fkey",
        "outbox_event_elder_id_fkey",
        "outbox_event_actor_id_fkey",
    ]

    async with test_engine.begin() as conn:
        all_fks: list[str] = []
        for table in _CORE_TABLES:
            fks = await conn.run_sync(_get_foreign_keys, table)
            all_fks.extend(fks)

    for fk in expected_fks:
        assert (
            fk in all_fks
        ), f"Expected FK constraint '{fk}' not restored after round-trip. Found: {all_fks}"


@pytest.mark.asyncio
async def test_baseline_full_downgrade_to_base(test_engine):
    """Verify downgrading from head all the way to base removes everything.

    Validates: Requirement 16.5
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(_drop_all_tables)

    # Upgrade to head
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_upgrade, "head")

    # Downgrade to base (removes all migrations)
    async with test_engine.begin() as conn:
        await conn.run_sync(_run_downgrade, "base")

    # Verify no application tables remain
    async with test_engine.begin() as conn:
        tables = await conn.run_sync(_get_tables)
        assert tables == [], f"Expected no tables after downgrade to base, got {tables}"

    # Verify the eldercare_ai schema itself is gone
    async with test_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
            {"schema": SCHEMA_NAME},
        )
        assert (
            result.first() is None
        ), "eldercare_ai schema should not exist after downgrade to base"

    # Verify alembic_version is empty
    async with test_engine.begin() as conn:
        version = await conn.run_sync(_get_alembic_version)
        assert version is None, f"Expected no version after downgrade to base, got '{version}'"
