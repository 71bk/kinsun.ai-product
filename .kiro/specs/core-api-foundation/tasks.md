# Implementation Plan: Core API Foundation

## Overview

This plan implements the greenfield `services/core-api/` service foundation — project scaffolding, async database connectivity, base ORM patterns, health/readiness endpoints, middleware, authentication abstractions, transactional outbox write-path, and testing infrastructure. Tasks are ordered for incremental buildability: each task builds on previous outputs, ending with full wiring and verification.

## Tasks

- [x] 1. Project scaffolding and dependency management
  - [x] 1.1 Create pyproject.toml with pinned dependencies and tool configuration
    - Create `services/core-api/pyproject.toml` with all pinned dependencies (fastapi, sqlalchemy, pydantic, pydantic-settings, alembic, pytest, pytest-asyncio, hypothesis, uvicorn, asyncpg, httpx, ruff, pytest-cov)
    - Configure `[tool.pytest.ini_options]` with testpaths, asyncio_mode
    - Configure `[tool.ruff]` with line-length=100, import sorting, unused imports rules
    - Configure `[tool.ruff.format]` for consistent formatting
    - _Requirements: 1.1, 18.3, 18.4, 18.5_

  - [x] 1.2 Create directory structure and __init__.py files
    - Create all 11 packages under `services/core-api/app/`: api, core, db, domain, models, repositories, schemas, services, policies, events, middleware — each with `__init__.py`
    - Create `services/core-api/app/__init__.py` and `services/core-api/app/main.py` (placeholder)
    - Create test directories: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/unit/conftest.py`, `tests/integration/__init__.py`, `tests/integration/conftest.py`
    - Create `services/core-api/alembic/` directory with empty `versions/` subdirectory
    - _Requirements: 1.2, 1.4, 1.6_

  - [x] 1.3 Create Dockerfile
    - Python 3.12 slim base image
    - Non-root user (UID >= 1000)
    - Expose port 8000
    - ENTRYPOINT running uvicorn
    - _Requirements: 1.3_

  - [x] 1.4 Create Docker Compose and .env files
    - Create `docker-compose.yml` at repository root with PostgreSQL 16 service
    - Named volume `kinsun_pgdata`, port 5432:5432, pg_isready healthcheck (interval 5s, start_period 30s, retries 5)
    - Environment defaults: POSTGRES_DB=kinsun, POSTGRES_USER=kinsun, POSTGRES_PASSWORD=kinsun_dev
    - Create `services/core-api/.env.example` with all required variable names and placeholder values
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 18.1_

- [x] 2. Configuration and settings management
  - [x] 2.1 Implement Settings Manager (app/core/config.py)
    - Pydantic BaseSettings with AppEnv enum (development, production)
    - All fields: app_env, app_title, app_version, docs_url, host, port, database_url, db_pool_size, db_max_overflow, test_database_url, database_password, fake_auth_enabled
    - Field validators: database_url must match `postgresql+asyncpg://`, port 1-65535
    - Conditional .env loading (development only)
    - Secret field redaction in __repr__, __str__, model_dump (fields containing "password", "secret", "key" → "***")
    - `@lru_cache` singleton pattern via `get_settings()`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 2.2 Write unit tests for Settings Manager
    - Test valid configuration loading
    - Test missing required fields raise startup error
    - Test invalid DATABASE_URL scheme rejection
    - Test port range validation
    - Test secret redaction in repr/str/model_dump
    - Test singleton behavior
    - Test .env file loading only in development mode
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 3. Database engine and session management
  - [x] 3.1 Implement Database Engine (app/db/engine.py)
    - `DatabaseEngine` class with async SQLAlchemy engine creation
    - Connection pooling (pool_size, max_overflow from settings)
    - `check_connectivity()` method (SELECT 1)
    - `is_ready` property for degraded mode tracking
    - `dispose()` with 30-second timeout
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7_

  - [x] 3.2 Implement session dependency (app/db/session.py)
    - Request-scoped async session generator
    - Check `db_engine.is_ready` before yielding — raise `ServiceUnavailableError` (503) if not ready
    - Auto-commit on success, auto-rollback on exception
    - _Requirements: 3.2, 3.4, 3.6_

  - [x]* 3.3 Write unit tests for Database Engine
    - Test engine creation with valid settings
    - Test `is_ready` state transitions
    - Test session rollback on exception
    - Test 503 raised when DB not ready
    - _Requirements: 3.1, 3.2, 3.4, 3.6_

- [x] 4. Base ORM models and mixins
  - [x] 4.1 Implement Base, BaseModel, TenantScopedMixin, OptimisticConcurrencyMixin (app/db/base.py)
    - `Base` (DeclarativeBase)
    - `BaseModel` (abstract): id (UUID PK, server-default gen_random_uuid), created_at (timestamptz, server_default now), updated_at (timestamptz, server_default now, onupdate now), version (int, server_default 1)
    - `TenantScopedMixin`: tenant_id (UUID, non-nullable, indexed)
    - `OptimisticConcurrencyMixin`: version-check update logic raising `OptimisticConcurrencyError`
    - `before_flush` event listener for tenant_id immutability (raises `TenantImmutabilityError`)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 4.2 Implement domain exception hierarchy (app/core/exceptions.py)
    - DomainException base, NotFoundError, ConflictError, OptimisticConcurrencyError, ValidationError (with details), AuthorizationDeniedError, AuthenticationError, ServiceUnavailableError, TenantScopeError, TenantImmutabilityError
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 5. Checkpoint - Verify base infrastructure
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Response envelopes and error handling
  - [x] 6.1 Implement response envelopes (app/core/envelopes.py)
    - `ResponseMeta` (correlation_id, timestamp)
    - `SuccessEnvelope[T]` (data: T, meta: ResponseMeta)
    - `ValidationDetail` (field, reason)
    - `ErrorBody` (code, message, correlation_id, details)
    - `ErrorEnvelope` (error: ErrorBody)
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 6.2 Implement error handler registration (app/api/error_handlers.py or app/main.py)
    - Exception-to-status mapping: NotFoundError→404, ConflictError→409, ValidationError→422, AuthorizationDeniedError→404, AuthenticationError→401, ServiceUnavailableError→503, TenantScopeError→401
    - Build ErrorEnvelope from exception with correlation_id
    - Production mode: strip stack traces, SQL, internal paths from responses
    - Self-healing: if error handler fails, return minimal 500 with correlation_id
    - _Requirements: 8.4, 8.5, 8.6, 9.1, 9.2, 9.3, 9.4_

  - [x]* 6.3 Write unit tests for envelopes and error handling
    - Test error envelope structure for each exception type
    - Test production mode redaction
    - Test error handler self-failure returns minimal 500
    - Test AuthorizationDeniedError maps to 404
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.1, 9.2, 9.3, 9.4_

- [x] 7. Request logging middleware
  - [x] 7.1 Implement Request Logger middleware (app/middleware/logging.py)
    - Structured JSON log for every request: method, path, status_code, duration_ms, correlation_id, ISO 8601 timestamp
    - Extract `x-correlation-id` from header or generate UUID v4
    - Set correlation_id in contextvars for downstream propagation
    - Attach correlation_id to response headers
    - Never log request/response bodies, auth headers, cookies, sensitive params
    - On 4xx/5xx: include tenant_id and actor_id if available
    - Log emission failure does not interrupt request processing
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

  - [x]* 7.2 Write unit tests for Request Logger
    - Test correlation_id generation when header missing
    - Test correlation_id passthrough when header present
    - Test sensitive headers not logged
    - Test duration measurement
    - Test tenant_id/actor_id inclusion on error responses
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [x] 8. Authentication abstractions
  - [x] 8.1 Implement auth module (app/middleware/auth.py)
    - `ActorContext` frozen dataclass: actor_id (UUID), actor_role (str), tenant_id (UUID)
    - `Authenticator` ABC with `authenticate(request) -> ActorContext`
    - `FakeAuthenticator` with configurable ActorContext (for tests and local dev)
    - `get_authenticator()` factory — environment-guarded:
      - Production: require real authenticator or raise `NoAuthenticatorConfiguredError` (fail closed)
      - Development + FAKE_AUTH_ENABLED=true: return FakeAuthenticator
      - Development without fake auth: require real authenticator or fail
    - `get_actor_context()` FastAPI dependency for protected routes
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

  - [x]* 8.2 Write unit tests for authentication
    - Test ActorContext immutability
    - Test FakeAuthenticator returns configured values
    - Test get_authenticator() factory: dev with fake enabled, dev without fake, production without real → error
    - Test get_actor_context() rejects when authenticator raises AuthenticationError → 401
    - Test actor context NOT derived from request body/params/headers
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

- [x] 9. Tenant scope and repository layer
  - [x] 9.1 Implement BaseRepository (app/repositories/base.py)
    - Constructor takes `session: AsyncSession` and `tenant_id: UUID` explicitly
    - `get_by_id(model_class, entity_id)` with WHERE id=$1 AND tenant_id=$2
    - `list_all(model_class, limit, offset)` with WHERE tenant_id=$1
    - All queries include explicit tenant predicate
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x]* 9.2 Write unit tests for tenant scope
    - Test repository always includes tenant filter
    - Test tenant_id only from ActorContext, never request params
    - Test missing/null tenant_id raises TenantScopeError
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [x] 10. Health and readiness endpoints
  - [x] 10.1 Implement health endpoint (app/api/health.py)
    - GET /health returns 200 with {"status": "ok", "uptime_seconds": N}
    - No DB dependency, no auth required
    - Non-GET methods return 405
    - Respond within 100ms
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 10.2 Implement readiness endpoint (app/api/ready.py)
    - GET /ready checks DB connectivity (SELECT 1) with 3s timeout
    - Returns 200 {"status": "ready", "database": "connected"} on success
    - Returns 503 {"status": "not_ready", "database": "unavailable"} on failure/timeout
    - No auth required
    - Non-GET methods return 405
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 10.3 Write integration tests for health and readiness
    - Test health returns 200 with expected body
    - Test health non-GET returns 405
    - Test ready returns 200 when DB available
    - Test ready returns 503 when DB unavailable
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 11. Checkpoint - Verify middleware and endpoints
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Transactional outbox
  - [x] 12.1 Implement OutboxEntry model (app/models/outbox.py)
    - SQLAlchemy model inheriting from `Base` (NOT BaseModel)
    - Columns: event_id (UUID PK), event_type (varchar 255), aggregate_id (UUID), tenant_id (UUID), payload (JSONB), created_at (timestamptz, server_default now), published (boolean, default false)
    - Index on (published, created_at) for relay polling
    - _Requirements: 13.1_

  - [x] 12.2 Implement outbox_writer (app/events/outbox_writer.py)
    - `write_outbox_entry(session, event_type, aggregate_id, tenant_id, payload, event_id=None)`
    - Validate payload size (max 256 KB), required fields not null/empty
    - INSERT ... ON CONFLICT DO NOTHING for idempotent writes
    - Written within caller's transaction (same session)
    - _Requirements: 13.2, 13.3, 13.4, 13.5, 13.7_

  - [x] 12.3 Implement EventPublisher ABC and FakePublisher (app/events/publisher.py)
    - `EventPublisher` ABC with `publish(event_type, aggregate_id, tenant_id, payload)`
    - `FakePublisher` in-memory implementation collecting events in a list
    - _Requirements: 13.2, 13.6_

  - [x]* 12.4 Write unit tests for outbox validation
    - Test payload exceeding 256 KB is rejected
    - Test required field validation (null/empty event_type, aggregate_id, tenant_id)
    - Test FakePublisher collects events
    - _Requirements: 13.1, 13.2, 13.5, 13.6_

- [x] 13. Alembic configuration and initial migration
  - [x] 13.1 Configure Alembic for async (alembic.ini, alembic/env.py, alembic/script.py.mako)
    - alembic.ini with script_location and sqlalchemy.url placeholder
    - env.py with async engine, metadata from Base, model imports
    - Support autogenerate, upgrade head, downgrade -1
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 1.6_

  - [x] 13.2 Generate initial migration for outbox table
    - Run `alembic revision --autogenerate -m "initial_outbox"` (or create manually)
    - Verify migration creates outbox table with all columns and index
    - Include downgrade (DROP TABLE outbox)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 13.1_

- [x] 14. Application entrypoint and lifecycle
  - [x] 14.1 Implement app/main.py with lifespan and create_app
    - FastAPI app with title, version, docs_url from settings
    - `lifespan` async context manager: startup (settings → engine → connectivity check → middleware → routes), shutdown (dispose in reverse)
    - Degraded mode: if DB unreachable at startup, log warning, continue (health=200, ready=503, DB routes=503)
    - Fatal startup error (config invalid): log to stderr, exit non-zero within 10s
    - OpenAPI docs enabled only in development; 404 for /docs, /redoc, /openapi.json in production
    - Register exception handlers
    - Log ready message with host:port on successful startup
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8_

- [x] 15. Checkpoint - Full application runs
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Testing infrastructure
  - [x] 16.1 Implement integration test conftest (tests/integration/conftest.py)
    - Session-scoped event loop fixture
    - Session-scoped test engine (TEST_DATABASE_URL)
    - Run Alembic upgrade head as session-scoped setup
    - Per-test `db_session` fixture with transaction rollback
    - `committed_session` fixture for tests needing committed data with cleanup
    - AsyncClient fixture with FakeAuthenticator dependency override
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7_

  - [x] 16.2 Implement unit test conftest (tests/unit/conftest.py)
    - Ensure no DB connection, no network calls
    - Provide mock settings fixture
    - Provide mock session fixture (if needed)
    - _Requirements: 16.1, 16.2_

  - [x] 16.3 Write migration verification tests (tests/integration/test_migrations.py)
    - Test upgrade from empty DB to head succeeds
    - Test downgrade -1 from head succeeds
    - Test upgrade → downgrade → upgrade round-trip produces same state
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

- [x] 17. Property-based tests (mandatory)
  - [x]* 17.1 Write property test for identifier and timestamp invariants
    - **Property 1: Identifier and timestamp invariants**
    - For any entity persisted through ORM: id is valid UUID, created_at non-null, updated_at non-null, created_at <= updated_at
    - Use Hypothesis with min 100 examples
    - **Validates: Requirements 4.1, 4.3**

  - [x] 17.2 Write property test for tenant-scope non-expansion
    - **Property 2: Tenant-scope non-expansion**
    - For any query via BaseRepository(tenant_id=X), results never contain tenant_id != X
    - Use Hypothesis with min 100 examples
    - **Validates: Requirements 4.7, 12.2**

  - [x]* 17.3 Write property test for optimistic version monotonicity
    - **Property 3: Optimistic version monotonicity**
    - Update with expected_version == current → success, version = current + 1; expected_version != current → OptimisticConcurrencyError
    - Use Hypothesis with min 100 examples
    - **Validates: Requirements 4.5**

  - [x]* 17.4 Write property test for transaction rollback guarantee
    - **Property 4: Transaction rollback guarantee**
    - Any exception after DB modifications within a session → session rolled back, no partial writes persist
    - Use Hypothesis with min 100 examples
    - **Validates: Requirements 3.6**

  - [x] 17.5 Write property test for outbox atomicity
    - **Property 5: Outbox atomicity**
    - Committed transaction: both entity and outbox entry visible; rolled-back transaction: neither persisted
    - Use Hypothesis with min 100 examples
    - **Validates: Requirements 13.3, 13.4**

  - [x]* 17.6 Write property test for outbox duplicate prevention
    - **Property 6: Outbox duplicate prevention**
    - Writing same event_id twice → exactly one row, no error on second write
    - Use Hypothesis with min 100 examples
    - **Validates: Requirements 13.7**

- [x] 18. Developer experience and documentation
  - [x] 18.1 Create services/core-api/README.md
    - Document: install dependencies, start dev server, run migrations, run unit/integration tests, shut down Docker
    - _Requirements: 18.2_

  - [x] 18.2 Final lint and format verification
    - Ensure `ruff check .` produces zero errors
    - Ensure `ruff format --check .` passes
    - _Requirements: 18.4, 18.5_

- [x] 19. Final checkpoint - All tests pass and linting clean
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The design specifies BaseModel (id, timestamps, version) separated from TenantScopedMixin — task 4.1 reflects this
- Repositories take explicit tenant_id parameter (not contextvars) — task 9.1 reflects this
- FakeAuthenticator is environment-guarded (never production default) — task 8.1 reflects this
- Outbox is write-path only (no relay/publisher in API transaction) — tasks 12.1-12.3 reflect this
- Health endpoint has no DB dependency; Ready endpoint checks DB — tasks 10.1-10.2 reflect this
- DB-dependent endpoints return 503 in degraded mode — task 3.2 session dependency guard

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "4.2"] },
    { "id": 3, "tasks": ["2.2", "3.1", "4.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "7.1"] },
    { "id": 6, "tasks": ["7.2", "8.1", "9.1"] },
    { "id": 7, "tasks": ["8.2", "9.2", "10.1", "10.2"] },
    { "id": 8, "tasks": ["10.3", "12.1"] },
    { "id": 9, "tasks": ["12.2", "12.3"] },
    { "id": 10, "tasks": ["12.4", "13.1"] },
    { "id": 11, "tasks": ["13.2"] },
    { "id": 12, "tasks": ["14.1"] },
    { "id": 13, "tasks": ["16.1", "16.2"] },
    { "id": 14, "tasks": ["16.3", "17.1", "17.2", "17.3"] },
    { "id": 15, "tasks": ["17.4", "17.5", "17.6"] },
    { "id": 16, "tasks": ["18.1", "18.2"] }
  ]
}
```
