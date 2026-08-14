# Requirements Document

> **2026-08-14 domain-boundary note:** This foundation remains valid, but `Actor_Context` and
> tenant-scoped repository primitives do not imply `Actor == Elder` or that every Elder must inherit a
> permanent single-tenant ownership model. Subsequent Elder features must follow
> [ADR 0013](../../../docs/adr/0013-separate-account-elder-enrollment-entitlement.md) and
> [Spec 17](../../../docs/spec/17智慧長照%20AI%20陪伴系統－Account、Elder、Enrollment%20與%20Service%20Entitlement%20v0.1.md):
> Actor is the authenticated principal; Elder may have no account; service context is resolved through
> Enrollment and authorization, not inferred from client input.

## Introduction

This document defines the requirements for the foundational scaffolding of the **core-api** service in kinsun.ai. The core-api is the primary backend API service built with Python 3.12 and FastAPI. This foundation covers project setup, configuration management, async database connectivity, health and readiness endpoints, standard response envelopes, middleware extension points, error handling, testing infrastructure, and the base patterns (transactional outbox persistence, optimistic concurrency, tenant isolation abstractions) that all subsequent domain features will build upon.

This specification explicitly excludes real authentication provider integration (Cognito), complete RBAC/ABAC policy evaluation, EventBridge/SQS messaging, and domain-specific authorization rules. Those concerns will be addressed in subsequent feature specifications that build on this foundation.

## Glossary

- **Core_API**: The primary FastAPI backend service providing HTTP endpoints for the kinsun.ai platform.
- **Settings_Manager**: The component responsible for loading, validating, and exposing application configuration from environment variables and secrets.
- **Database_Engine**: The async SQLAlchemy engine and session factory providing connection pooling and transactional access to PostgreSQL.
- **Health_Endpoint**: The HTTP endpoint that reports whether the API process is running, independent of downstream dependencies.
- **Readiness_Endpoint**: The HTTP endpoint that reports whether the service can accept traffic by verifying database connectivity.
- **Response_Envelope**: The standardized JSON wrapper structure used for all API responses, providing consistent data and error formats.
- **Actor_Context**: A server-side data class containing actor_id (UUID), actor_role (string), and tenant_id (UUID) — representing trusted identity information derived from authentication. In the foundation, this is populated by a pluggable authenticator interface.
- **Auth_Dependency**: A FastAPI dependency that resolves Actor_Context for protected routes via a pluggable authenticator interface, allowing real authentication to be added later without changing route signatures.
- **Tenant_Scope**: The mechanism that ensures all data access within a request is filtered to the tenant identified in Actor_Context, enforced at the repository layer.
- **Error_Handler**: The component that transforms unhandled exceptions into structured, safe HTTP error responses using the standard error envelope.
- **Base_Model**: The SQLAlchemy declarative base class providing common columns (id, tenant_id, created_at, updated_at, version) to all ORM models.
- **Outbox_Entry**: The SQLAlchemy model representing a domain event persisted to the transactional outbox table within the same database transaction as the originating command.
- **Event_Publisher**: An abstract base class defining the interface for publishing domain events; concrete implementations (EventBridge, SQS) will be provided in later specs.
- **Fake_Publisher**: An in-memory implementation of Event_Publisher that collects events for use in tests.
- **Migration_Runner**: Alembic-based component that applies database schema migrations.
- **Request_Logger**: The middleware component that logs structured request and response metadata for observability.
- **Test_Database**: A separate PostgreSQL database (or schema) used exclusively for integration tests, isolated from development and production databases.

## Requirements

### Requirement 1: Project Structure and Dependency Management

**User Story:** As a developer, I want a well-organized project structure with pinned dependencies, so that I can build domain features on a stable, reproducible foundation.

#### Acceptance Criteria

1. THE Core_API SHALL define all Python dependencies with exact pinned versions (using == operator, no ^, ~, >=, or * ranges) in services/core-api/pyproject.toml, including at minimum: fastapi, sqlalchemy, pydantic, alembic, pytest, uvicorn, asyncpg, httpx, and ruff.
2. THE Core_API SHALL organize source code under services/core-api/app/ into the following packages, each containing an __init__.py file: api, core, db, domain, models, repositories, schemas, services, policies, events, and middleware — totaling exactly 11 packages.
3. THE Core_API SHALL include a Dockerfile based on Python 3.12 that creates and runs the application as a non-root user (UID ≥ 1000), exposes exactly one HTTP port (default 8000), and defines an explicit ENTRYPOINT or CMD directive that starts the application.
4. THE Core_API SHALL include test directories at services/core-api/tests/unit/ and services/core-api/tests/integration/, each containing an __init__.py file, and a top-level services/core-api/tests/__init__.py file.
5. WHEN pytest is invoked from the services/core-api/ directory without path arguments, THE Core_API SHALL allow pytest to discover and collect tests from both tests/unit/ and tests/integration/ directories, confirmed by pytest --collect-only returning zero exit code with both directories listed.
6. THE Core_API SHALL include an Alembic directory at services/core-api/alembic/ containing an env.py file and a versions/ subdirectory, with an alembic.ini configuration file at services/core-api/alembic.ini that references the correct script_location and sqlalchemy.url placeholder.
7. IF a developer runs `pip install -e .` from the services/core-api/ directory, THEN THE Core_API SHALL install successfully without dependency resolution conflicts, verified by a zero exit code.

### Requirement 2: Application Configuration

**User Story:** As a developer, I want centralized, validated configuration loaded from environment variables, so that the service behaves correctly across local development and production environments.

#### Acceptance Criteria

1. WHEN the application starts with APP_ENV=development, THE Settings_Manager SHALL load configuration values from environment variables and additionally from a .env file located in the services/core-api/ directory, with environment variables taking precedence over .env file values.
2. WHEN the application starts with APP_ENV=production, THE Settings_Manager SHALL load configuration values exclusively from environment variables and SHALL NOT read from any .env file.
3. WHEN the application starts, THE Settings_Manager SHALL validate all configuration values using Pydantic, rejecting any value that does not conform to its declared type or constraints (including non-empty strings for required fields and valid integer ranges for port numbers between 1 and 65535).
4. IF a required configuration value is missing or fails validation, THEN THE Settings_Manager SHALL raise a startup error within 5 seconds that identifies the variable name and the validation failure reason in the error output, and SHALL prevent the application from binding to a port or accepting HTTP requests.
5. THE Settings_Manager SHALL support exactly two configuration profiles — development and production — selected via the APP_ENV environment variable, defaulting to development if APP_ENV is not set.
6. THE Settings_Manager SHALL redact secret values (any field whose name contains "password", "secret", or "key") by replacing them with the fixed string "***" in all __repr__, __str__, and model_dump outputs, ensuring the actual value never appears in log output or error tracebacks.
7. WHEN validation succeeds, THE Settings_Manager SHALL make the validated settings available as a process-lifetime singleton, returning the same object instance on every access within the same process.
8. THE Settings_Manager SHALL validate that the DATABASE_URL configuration value conforms to a valid PostgreSQL async URI format (scheme matching postgresql+asyncpg://) at startup, rejecting values that do not match with a descriptive validation error.

### Requirement 3: Async Database Connectivity

**User Story:** As a developer, I want an async database engine with connection pooling, so that the service can efficiently handle concurrent requests against PostgreSQL.

#### Acceptance Criteria

1. THE Database_Engine SHALL create an async SQLAlchemy engine using the `postgresql+asyncpg` connection scheme, connected to PostgreSQL using the connection string from Settings_Manager.
2. THE Database_Engine SHALL provide an async session factory that yields one scoped session per request lifecycle, where each session is bound to the originating request and is not shared across concurrent requests.
3. THE Database_Engine SHALL configure connection pooling with parameters loaded from Settings_Manager, defaulting to pool_size of 5 and max_overflow of 10 when not explicitly configured.
4. WHEN the database is unreachable at startup, THE Database_Engine SHALL log the connection failure, start the application in a degraded state where the Readiness_Endpoint reports non-ready status, and reject any request requiring database access with HTTP 503.
5. WHEN the application begins shutdown, THE Database_Engine SHALL close all connections and dispose of the engine pool, awaiting graceful connection close for a maximum of 30 seconds before forcing disposal.
6. WHEN a session completes its request lifecycle, THE Database_Engine SHALL ensure the session is either committed or rolled back before being returned to the connection pool, preventing session leaks.
7. THE Database_Engine SHALL use the asyncpg driver for all async communication with PostgreSQL.

### Requirement 4: Base ORM Model

**User Story:** As a developer, I want a base ORM model with standard columns, so that all domain entities share a consistent schema for identification, tenancy, auditing, and concurrency control.

#### Acceptance Criteria

1. THE Base_Model SHALL include a UUID primary key column generated server-side using a database-level default (not application-generated).
2. THE Base_Model SHALL include a tenant_id UUID column that is non-nullable and indexed for tenant-scoped entities.
3. THE Base_Model SHALL include a created_at column of timestamp-with-timezone type, populated automatically by the database on row insertion, and an updated_at column of timestamp-with-timezone type, populated automatically on insertion and updated automatically on each row modification.
4. THE Base_Model SHALL include a version integer column with a server default of 1 for optimistic concurrency control.
5. WHEN an entity is updated, THE Base_Model SHALL increment the version column by exactly 1, and IF the current version in the database does not match the expected version provided in the update, THEN THE Base_Model SHALL reject the update with an optimistic concurrency conflict error indicating a stale write.
6. THE Base_Model SHALL NOT allow tenant_id to be modified after initial creation of the row.
7. IF a query targets a tenant-scoped entity without providing a tenant_id filter, THEN THE Base_Model SHALL raise an error rather than returning unscoped results.

### Requirement 5: Database Migrations

**User Story:** As a developer, I want Alembic migrations configured for async PostgreSQL, so that schema changes are versioned, repeatable, and applied safely.

#### Acceptance Criteria

1. THE Migration_Runner SHALL use Alembic configured with async SQLAlchemy using the asyncpg driver, with the database connection string sourced from Settings_Manager.
2. THE Migration_Runner SHALL auto-detect model changes for migration generation, limited to models registered in Base_Model metadata; it SHALL NOT detect or generate migrations for external schemas outside Base_Model metadata.
3. WHEN a migration is applied, THE Migration_Runner SHALL record the current head revision in the alembic_version table in the database.
4. THE Migration_Runner SHALL support forward migration (upgrade) to the "head" target and single-step rollback (downgrade) using the "-1" target.
5. WHEN upgrade is executed and the database is already at head revision, THE Migration_Runner SHALL complete as a no-op without error.
6. IF a migration fails mid-execution, THEN THE Migration_Runner SHALL roll back that migration's transaction, report an error message indicating the failure cause, and preserve the alembic_version state as it was before the failed migration attempt.

### Requirement 6: Health Endpoint

**User Story:** As an operations engineer, I want a health endpoint that confirms the API process is running, so that orchestrators can detect process crashes independently of downstream dependencies.

#### Acceptance Criteria

1. WHEN an HTTP GET request is received at /health, THE Health_Endpoint SHALL return HTTP 200 with a JSON body containing a "status" field with value "ok".
2. THE Health_Endpoint SHALL NOT perform any database connectivity check or depend on the Database_Engine being available.
3. THE Health_Endpoint SHALL include an "uptime_seconds" field in the JSON response body representing elapsed seconds since process start, as a non-negative integer.
4. THE Health_Endpoint SHALL respond within 100 milliseconds under normal operating conditions.
5. THE Health_Endpoint SHALL be accessible without authentication and SHALL NOT require any request headers, query parameters, or request body.
6. WHEN an HTTP request with a method other than GET is received at /health, THE Health_Endpoint SHALL return HTTP 405.

### Requirement 7: Readiness Endpoint

**User Story:** As an operations engineer, I want a readiness endpoint that verifies database connectivity, so that load balancers can determine whether the service can accept traffic.

#### Acceptance Criteria

1. WHEN an HTTP GET request is received at /ready, THE Readiness_Endpoint SHALL verify database connectivity by executing a lightweight query (e.g., SELECT 1) against the Database_Engine.
2. WHEN the database connectivity check succeeds within 3 seconds, THE Readiness_Endpoint SHALL return HTTP 200 with a JSON body containing "status" set to "ready" and "database" set to "connected".
3. IF the database is unreachable or the connectivity check exceeds 3 seconds, THEN THE Readiness_Endpoint SHALL return HTTP 503 with a JSON body containing "status" set to "not_ready" and "database" set to "unavailable".
4. THE Readiness_Endpoint SHALL respond within 5 seconds, including the database connectivity check.
5. THE Readiness_Endpoint SHALL be accessible without authentication and SHALL NOT require any request headers, query parameters, or request body.
6. WHEN an HTTP request with a method other than GET is received at /ready, THE Readiness_Endpoint SHALL return HTTP 405.

### Requirement 8: Standard Response Envelopes

**User Story:** As a developer, I want standardized response formats for all API responses, so that API consumers can rely on a consistent structure for both success and error cases.

#### Acceptance Criteria

1. THE Response_Envelope SHALL define a success envelope format as a JSON object containing a "data" field (holding the response payload) and a "meta" field (holding metadata such as request correlation_id and timestamp).
2. THE Response_Envelope SHALL define an error envelope format as a JSON object containing an "error" field with nested "code" (string identifying the error category), "message" (human-readable description), and "correlation_id" (UUID v4 string matching the request correlation).
3. WHEN a validation error occurs, THE Response_Envelope SHALL include a "details" array within the "error" field, where each entry contains a "field" (the field name that failed validation) and a "reason" (description of the validation failure).
4. THE Core_API SHALL use the success envelope for all HTTP 2xx responses on API endpoints (excluding /health and /ready which use their own minimal format).
5. THE Core_API SHALL use the error envelope for all HTTP 4xx and 5xx responses on API endpoints.
6. WHILE the application is running in production mode, THE Response_Envelope SHALL exclude stack traces, internal file paths, SQL or query text, and database object names from all error envelope responses.

### Requirement 9: Structured Error Handling

**User Story:** As a developer, I want consistent error handling that maps exceptions to the standard error envelope, so that API consumers receive predictable error formats and sensitive details are never leaked.

#### Acceptance Criteria

1. WHEN an unhandled exception occurs, THE Error_Handler SHALL return an error envelope response containing a correlation_id (UUID v4 string), an error code (string identifying the error category), and a message (non-empty string describing the failure without exposing internal system details).
2. THE Error_Handler SHALL map domain exceptions to HTTP status codes as follows: not found → 404, conflict → 409, validation error → 422 with a details array, authorization denied → 403.
3. WHEN an authorization check fails on a request that targets a single resource identified by ID, THE Error_Handler SHALL return HTTP 404 with the same response structure as a not-found error to avoid revealing resource existence.
4. IF the Error_Handler itself raises an exception during error processing, THEN THE Error_Handler SHALL return HTTP 500 with a response containing only the correlation_id and a generic error code indicating an internal failure, and SHALL NOT expose details of the secondary failure.

### Requirement 10: Request Logging Middleware

**User Story:** As an operations engineer, I want structured request logging, so that I can trace requests, diagnose latency, and audit access patterns.

#### Acceptance Criteria

1. THE Request_Logger SHALL emit a structured JSON log entry for every completed HTTP request, including method, path, response status code, request duration in milliseconds, correlation_id, and ISO 8601 timestamp.
2. IF a request does not include a correlation_id in the request headers, THEN THE Request_Logger SHALL generate a UUID v4 correlation_id and assign it to the request before processing continues.
3. THE Request_Logger SHALL never log request or response bodies, authorization headers, cookie values, or query parameters containing tokens, passwords, or personal identifiers (as defined by the sensitive-fields configuration list).
4. THE Request_Logger SHALL propagate the correlation_id to all downstream log entries emitted within the same request scope by attaching it to the logging context.
5. IF log emission fails (e.g., I/O error writing to the log sink), THEN THE Request_Logger SHALL not interrupt request processing and SHALL increment an internal error counter observable via the health endpoint.
6. THE Request_Logger SHALL record request duration measured from the point the request is received to the point the response is fully sent, with millisecond precision.
7. WHEN the response status code is 4xx or 5xx, THE Request_Logger SHALL include the tenant_id (if resolved) and the authenticated actor_id (if available) in the log entry to support access auditing, without logging the authentication token itself.

### Requirement 11: Authentication Abstractions and Extension Points

**User Story:** As a developer, I want authentication abstractions with a pluggable interface and test doubles, so that I can develop and test protected routes without a real authentication provider.

#### Acceptance Criteria

1. THE Auth_Dependency SHALL define an Actor_Context data class containing actor_id (UUID), actor_role (string), and tenant_id (UUID) as immutable fields.
2. THE Auth_Dependency SHALL define a pluggable authenticator interface (abstract base class) with a method that accepts an HTTP request and returns an Actor_Context or raises an authentication error.
3. WHEN a protected route is invoked, THE Auth_Dependency SHALL resolve Actor_Context by calling the configured authenticator implementation, making Actor_Context available to the route handler via FastAPI dependency injection.
4. IF the authenticator raises an authentication error, THEN THE Auth_Dependency SHALL reject the request with HTTP 401 and an error envelope containing an error code and human-readable message without revealing internal system details.
5. THE Auth_Dependency SHALL provide a fake authenticator implementation for tests that returns a configurable Actor_Context without performing any token validation, allowing tests to simulate any actor identity.
6. THE Auth_Dependency SHALL derive actor_id, actor_role, and tenant_id exclusively from the authenticator result and SHALL ignore any actor_id, actor_role, or tenant_id values present in the request body, query parameters, or request headers.
7. WHEN a route is designated as unprotected in the application's route configuration, THE Auth_Dependency SHALL not be applied, allowing the request to proceed without Actor_Context.
8. THE Auth_Dependency SHALL apply authentication by default to all protected routes; only routes explicitly configured as unprotected SHALL be exempt.

### Requirement 12: Tenant Isolation Abstractions

**User Story:** As a developer, I want tenant isolation enforced at the repository layer with test support, so that queries are automatically scoped to the authenticated tenant without requiring real authentication infrastructure.

#### Acceptance Criteria

1. WHEN a request passes authentication, THE Tenant_Scope SHALL extract tenant_id from Actor_Context and make it available to all repositories and services executing within that request for query scoping.
2. IF a repository query targets a tenant-scoped entity without the tenant_id filter applied, THEN THE Tenant_Scope SHALL raise an error rather than returning unscoped results.
3. THE Tenant_Scope SHALL never accept tenant_id from query parameters, path parameters, request headers, or request bodies as the authoritative tenant identifier; tenant_id SHALL only be derived from Actor_Context.
4. IF Actor_Context does not contain a valid tenant_id (null or empty) on a protected route, THEN THE Tenant_Scope SHALL reject the request with HTTP 401 and an error envelope.
5. THE Tenant_Scope SHALL provide test utilities that allow integration tests to set a specific tenant_id in the request context without requiring a real authenticator, using the fake authenticator from Auth_Dependency.

### Requirement 13: Transactional Outbox Persistence

**User Story:** As a developer, I want an outbox persistence model and publisher interface, so that domain events can be reliably persisted alongside entity changes with a clear contract for future relay implementations.

#### Acceptance Criteria

1. THE Outbox_Entry SHALL be a SQLAlchemy model mapped to an outbox table containing columns: event_id (UUID, primary key), event_type (string, maximum 255 characters), aggregate_id (UUID), tenant_id (UUID), payload (JSON, maximum 256 KB), created_at (UTC timestamp with timezone), and published (boolean defaulting to false).
2. THE Event_Publisher SHALL define an abstract base class with a method to publish a domain event, accepting event_type, aggregate_id, tenant_id, and payload as parameters.
3. WHEN a domain event is persisted, THE Outbox_Entry SHALL be written within the same database transaction as the originating entity change, ensuring atomicity.
4. IF the originating transaction is rolled back, THEN THE Outbox_Entry SHALL NOT be persisted.
5. IF the payload exceeds 256 KB or any required field (event_id, event_type, aggregate_id, tenant_id, payload) is null or empty, THEN THE Event_Publisher SHALL reject the event with a validation error before attempting persistence.
6. THE Fake_Publisher SHALL provide an in-memory implementation of Event_Publisher that collects published events in a list, allowing tests to assert on event emission without database writes or external messaging infrastructure.
7. IF a domain event with a duplicate event_id already exists in the outbox table, THEN THE Outbox_Entry persistence SHALL skip insertion and succeed without raising an error (idempotent write).

### Requirement 14: Application Entrypoint and Lifecycle

**User Story:** As a developer, I want a well-defined application entrypoint with startup and shutdown hooks, so that resources are initialized and released in a controlled order.

#### Acceptance Criteria

1. THE Core_API SHALL create a FastAPI application instance with title, version, and docs_url sourced from Settings_Manager validated configuration values.
2. WHEN the application starts, THE Core_API SHALL initialize components in this exact order: (1) Settings_Manager, (2) Database_Engine (connection pool), (3) middleware stack (request logging, authentication dependency, tenant scope), and (4) route handler registration — with each step completing before the next begins.
3. IF any component fails to initialize during startup, THEN THE Core_API SHALL log a structured error message containing the component name and exception details to stderr, and SHALL terminate the process with a non-zero exit code within 10 seconds of the failure.
4. WHEN the application receives a shutdown signal (SIGTERM or SIGINT), THE Core_API SHALL dispose of resources in reverse initialization order (route handlers deregistered, middleware removed, Database_Engine connection pool closed, Settings_Manager released), completing all teardown within 30 seconds.
5. IF disposal of any single resource exceeds 10 seconds or raises an exception during shutdown, THEN THE Core_API SHALL log the error with the resource name and continue shutting down remaining resources without halting the shutdown sequence.
6. WHILE the application is running with APP_ENV=development, THE Core_API SHALL serve the interactive OpenAPI documentation at the configured docs_url path, returning HTTP 200 with a valid HTML response.
7. WHILE the application is running with APP_ENV=production, THE Core_API SHALL disable the OpenAPI schema endpoint and return HTTP 404 for requests to /docs, /redoc, and /openapi.json paths.
8. WHEN the application has completed startup initialization successfully, THE Core_API SHALL log a ready message including the bound host and port, indicating it is accepting HTTP connections.

### Requirement 15: Docker Compose Local Development Environment

**User Story:** As a developer, I want a Docker Compose configuration for local development, so that I can run PostgreSQL and supporting services with a single command.

#### Acceptance Criteria

1. THE Core_API SHALL provide a docker-compose.yml file (Compose specification version 3.8 or higher) at the repository root that defines a PostgreSQL 16 service with container port 5432 mapped to host port 5432.
2. THE Core_API SHALL configure the local PostgreSQL service with environment variables defaulting to POSTGRES_DB=kinsun, POSTGRES_USER=kinsun, and POSTGRES_PASSWORD=kinsun_dev, overridable via a .env file in the same directory as the docker-compose.yml file.
3. WHEN `docker compose up -d` is executed from the repository root, THE Core_API SHALL have the PostgreSQL service reach a healthy state, verified by a pg_isready-based healthcheck defined in the compose service configuration with an interval of no more than 5 seconds and a start_period of no more than 30 seconds.
4. THE Core_API SHALL define a named Docker volume (not an anonymous volume) for the PostgreSQL data directory, ensuring data persists across container stop/start cycles without data loss.
5. IF the PostgreSQL container fails its pg_isready health check after the configured start_period (maximum 30 seconds) and retries (maximum 5 attempts), THEN docker compose SHALL report the service status as unhealthy via `docker compose ps`.

### Requirement 16: Testing Infrastructure

**User Story:** As a developer, I want a well-configured testing infrastructure with database isolation, so that unit tests run without external dependencies and integration tests use a real database with proper transaction isolation.

#### Acceptance Criteria

1. THE Core_API SHALL configure pytest discovery in pyproject.toml or pytest.ini with testpaths pointing to tests/unit and tests/integration directories.
2. THE Core_API SHALL ensure unit tests in tests/unit/ execute without any database connection, network calls, or Docker dependencies.
3. THE Core_API SHALL provide integration test fixtures that connect to a Test_Database identified by a separate DATABASE_URL (e.g., TEST_DATABASE_URL environment variable), distinct from the development and production database URLs.
4. WHEN an integration test executes, THE Core_API SHALL wrap each test case in a database transaction that is rolled back after the test completes, ensuring test isolation without residual data.
5. IF a test requires committed data visible to concurrent connections, THE Core_API SHALL provide an alternative fixture that commits the transaction and performs explicit cleanup after the test.
6. THE Core_API SHALL provide a conftest.py in tests/integration/ that creates an async database session bound to the Test_Database and provides it as a pytest fixture.
7. THE Core_API SHALL ensure the Test_Database schema is created by running Alembic migrations (upgrade head) as part of the integration test setup, either via a session-scoped fixture or a test preparation script.

### Requirement 17: Migration Verification

**User Story:** As a developer, I want automated verification that migrations can be applied and rolled back cleanly, so that schema changes do not break deployment pipelines.

#### Acceptance Criteria

1. THE Core_API SHALL include an integration test that verifies Alembic upgrade from an empty database to the head revision completes without error.
2. THE Core_API SHALL include an integration test that verifies Alembic downgrade from head revision by one step (downgrade -1) completes without error for each migration.
3. WHEN upgrade followed by downgrade followed by upgrade is executed, THE Migration_Runner SHALL produce a database schema identical to a single upgrade to head, verifiable by comparing the alembic_version table state.
4. IF a migration contains a destructive operation (DROP TABLE, DROP COLUMN), THE Migration_Runner SHALL still support downgrade for that migration by including the reverse operation in the downgrade function.

### Requirement 18: Developer Experience

**User Story:** As a developer, I want clear documentation and tooling configuration, so that I can onboard quickly and maintain consistent code quality.

#### Acceptance Criteria

1. THE Core_API SHALL include a .env.example file at services/core-api/.env.example containing all required environment variable names with placeholder values (e.g., DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/kinsun) and no real credentials.
2. THE Core_API SHALL include a README.md at services/core-api/README.md documenting commands for: installing dependencies, starting the development server, running database migrations, running tests (unit and integration separately), and shutting down Docker services.
3. THE Core_API SHALL configure ruff (or equivalent Python linter/formatter) in pyproject.toml with rules for import sorting, unused imports, line length (maximum 100 characters), and basic style enforcement.
4. WHEN `ruff check .` is executed from the services/core-api/ directory on the initial codebase, THE Core_API SHALL produce zero linting errors (the generated code must be lint-clean).
5. THE Core_API SHALL include a ruff format configuration in pyproject.toml so that `ruff format --check .` passes without modifications needed on the initial codebase.
