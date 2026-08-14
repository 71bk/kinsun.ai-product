# Design Document: Core API Foundation

> **2026-08-14 domain-boundary note:** The `TenantScopedMixin` and `ActorContext` examples are
> infrastructure patterns, not a final Elder ownership decision. New Elder-domain work must follow
> [ADR 0013](../../../docs/adr/0013-separate-account-elder-enrollment-entitlement.md)／
> [Spec 17](../../../docs/spec/17智慧長照%20AI%20陪伴系統－Account、Elder、Enrollment%20與%20Service%20Entitlement%20v0.1.md).
> In particular, Actor and Elder are separate, an Elder may have no Actor, and multi-context service
> participation is represented by Enrollment. Existing foundation tasks remain historical completion
> evidence and are not reopened by this note.

## Overview

This document defines the technical design for the **core-api** service foundation — the scaffolding upon which all kinsun.ai domain features will be built. The design covers project structure, configuration management, async database connectivity with connection pooling, base ORM patterns (optimistic concurrency, tenant isolation via mixin), health/readiness endpoints, standard response envelopes, structured error handling, request logging middleware, authentication abstractions with environment-guarded safety, transactional outbox persistence (write-path only), application lifecycle management, local development environment, and testing infrastructure.

### Design Goals

1. **Greenfield correctness** — every module starts clean with no legacy constraints
2. **Async-first** — all I/O paths use async/await (FastAPI + SQLAlchemy 2 async + asyncpg)
3. **Tenant isolation by default** — repository layer enforces scoping via explicit tenant_id parameter; impossible to accidentally query cross-tenant
4. **Testability** — every component has a clear interface allowing test doubles
5. **Extensibility** — authentication, event publishing, and authorization are pluggable interfaces that later specs will fill with real implementations
6. **Fail-closed in production** — no fake/test authenticators silently becoming the production default

### Scope Exclusions

The following are explicitly **out of scope** for this foundation specification:

- No Elder, Consent, Assignment domain entities
- No RBAC or ABAC policy evaluation logic
- No Cognito or real authentication provider integration
- No EventBridge or SQS message relay
- No domain-specific authorization rules

These will be addressed in subsequent feature specifications that build on this foundation.

### Technology Stack

| Concern | Technology |
|---------|-----------|
| Language | Python 3.12 |
| HTTP Framework | FastAPI |
| ORM | SQLAlchemy 2 (async) |
| DB Driver | asyncpg |
| Validation / Settings | Pydantic v2 |
| Migrations | Alembic (async) |
| Testing | pytest + pytest-asyncio + httpx |
| Linting | ruff |
| Local DB | PostgreSQL 16 via Docker Compose |
| Container | Python 3.12 slim base image |


## Architecture

### High-Level Component Diagram

```mermaid
graph TD
    subgraph "HTTP Layer"
        Client[HTTP Client]
        FW[FastAPI Application]
    end

    subgraph "Middleware Stack"
        RL[Request Logger]
        AD[Auth Dependency]
    end

    subgraph "Application Layer"
        Routes[Route Handlers]
        Services[Application Services]
        Policies[Authorization Policies]
    end

    subgraph "Domain Layer"
        Domain[Domain Logic]
        Events[Domain Events]
    end

    subgraph "Data Layer"
        Repos[Repositories]
        Models[ORM Models]
        Outbox[Outbox Writer]
        Engine[Database Engine]
    end

    subgraph "Infrastructure"
        PG[(PostgreSQL 16)]
        Alembic[Migration Runner]
    end

    Client --> FW
    FW --> RL --> AD --> Routes
    Routes --> Services
    Services --> Policies
    Services --> Domain
    Services --> Repos
    Services --> Events
    Repos --> Models
    Repos --> Engine
    Events --> Outbox
    Outbox --> Engine
    Engine --> PG
    Alembic --> PG
```

### Request Flow Sequence

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as Middleware
    participant R as Route Handler
    participant S as Service
    participant Repo as Repository
    participant DB as PostgreSQL

    C->>MW: HTTP Request
    MW->>MW: Generate/extract correlation_id
    MW->>MW: Authenticate → ActorContext
    MW->>R: Forward with ActorContext
    R->>R: Validate request (Pydantic)
    R->>S: Call service method (pass tenant_id from ActorContext)
    S->>Repo: Data operation (explicit tenant_id param)
    Repo->>DB: SQL with WHERE tenant_id = $1
    DB-->>Repo: Result
    Repo-->>S: Domain entities
    S-->>R: Result
    R-->>MW: Response
    MW->>MW: Log request (structured JSON)
    MW-->>C: HTTP Response (envelope)
```

### Application Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Initializing
    Initializing --> SettingsLoaded: Load & validate config
    SettingsLoaded --> EngineReady: Create DB engine + pool
    EngineReady --> MiddlewareRegistered: Register middleware
    MiddlewareRegistered --> RoutesRegistered: Register routes
    RoutesRegistered --> Running: Bind port, log ready
    Running --> ShuttingDown: SIGTERM / SIGINT
    ShuttingDown --> [*]: Dispose in reverse order

    Initializing --> Failed: Config validation error
    SettingsLoaded --> Degraded: DB unreachable
    Degraded --> Running: Accept traffic (health=200, ready=503, DB routes=503)
    Failed --> [*]: Exit non-zero
```

**Degraded Mode Behavior:**
- **GET /health** always returns HTTP 200 while the process is alive. It does NOT access the database.
- **GET /ready** returns HTTP 503 when database connectivity is unavailable.
- **Database-dependent endpoints** return HTTP 503 (ServiceUnavailableError) when the DB is unavailable. The session dependency checks engine readiness and raises `ServiceUnavailableError` before yielding a session.

## Components and Interfaces

### Project Layout

```
services/core-api/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Application entrypoint, lifespan
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py             # GET /health
│   │   ├── ready.py              # GET /ready
│   │   └── deps.py              # Shared FastAPI dependencies
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Settings_Manager (Pydantic BaseSettings)
│   │   ├── exceptions.py        # Domain exception hierarchy
│   │   └── envelopes.py         # Response envelope schemas
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py            # Async engine + session factory
│   │   ├── base.py              # Base_Model + TenantScopedMixin
│   │   └── session.py           # Request-scoped session dependency
│   ├── domain/
│   │   └── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── outbox.py            # Outbox_Entry model
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── base.py              # Base repository with explicit tenant_id
│   ├── schemas/
│   │   └── __init__.py
│   ├── services/
│   │   └── __init__.py
│   ├── policies/
│   │   └── __init__.py
│   ├── events/
│   │   ├── __init__.py
│   │   ├── publisher.py         # Event_Publisher ABC + Fake_Publisher
│   │   └── outbox_writer.py     # Write outbox entries in transaction
│   └── middleware/
│       ├── __init__.py
│       ├── logging.py           # Request_Logger middleware
│       └── auth.py              # Auth_Dependency + Authenticator interface
├── alembic/
│   ├── env.py                   # Async Alembic environment
│   ├── script.py.mako
│   └── versions/
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Root conftest
│   ├── unit/
│   │   ├── __init__.py
│   │   └── conftest.py
│   └── integration/
│       ├── __init__.py
│       └── conftest.py          # DB fixtures, transaction rollback
├── alembic.ini
├── pyproject.toml
├── Dockerfile
├── .env.example
└── README.md
```


### Module: Settings Manager (`app/core/config.py`)

**Responsibility:** Load, validate, and expose application configuration as a process-lifetime singleton.

```python
from pydantic_settings import BaseSettings
from pydantic import field_validator, Field
from functools import lru_cache
from enum import Enum


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    In development mode, also reads from .env file.
    Secret fields are redacted in repr/str/model_dump.
    """
    # Application
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_title: str = "kinsun.ai Core API"
    app_version: str = "0.1.0"
    docs_url: str = "/docs"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)

    # Database
    database_url: str  # Required, validated as postgresql+asyncpg://
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)

    # Testing
    test_database_url: str = ""

    # Secrets (redacted in output)
    database_password: str = ""

    # Auth
    fake_auth_enabled: bool = False  # Only honored in development

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use postgresql+asyncpg:// scheme"
            )
        return v

    def __repr__(self) -> str:
        return self._redacted_repr()

    def _redacted_repr(self) -> str:
        """Replace secret fields with '***' in repr."""
        ...

    def model_dump(self, **kwargs) -> dict:
        """Override to redact secret fields."""
        ...


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-lifetime singleton for validated settings."""
    return Settings()
```

**Key Design Decisions:**
- Uses `pydantic-settings` for env-var loading with `.env` file support in development
- `@lru_cache` ensures singleton behavior (same instance on every call within the process)
- `.env` file loading is conditional on `APP_ENV=development`
- Secret field redaction uses field name matching (`password`, `secret`, `key`)
- Startup fails fast with descriptive Pydantic validation errors
- `fake_auth_enabled` flag is only honored when `app_env == DEVELOPMENT`


### Module: Database Engine (`app/db/engine.py`)

**Responsibility:** Create and manage the async SQLAlchemy engine with connection pooling and provide a request-scoped session factory.

```python
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)
from app.core.config import Settings


class DatabaseEngine:
    """Manages async SQLAlchemy engine lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self._engine: AsyncEngine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            echo=settings.app_env == "development",
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._ready: bool = False

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    @property
    def is_ready(self) -> bool:
        return self._ready

    async def check_connectivity(self) -> bool:
        """Execute SELECT 1 to verify database connectivity."""
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            self._ready = True
            return True
        except Exception:
            self._ready = False
            return False

    async def dispose(self, timeout: float = 30.0) -> None:
        """Close all connections and dispose engine pool."""
        ...
```

### Module: Session Dependency (`app/db/session.py`)

**Responsibility:** Provide a request-scoped async session that checks DB readiness before yielding.

```python
from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ServiceUnavailableError


async def get_db_session(
    db_engine: DatabaseEngine = Depends(get_db_engine),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield one scoped session per request.

    Raises ServiceUnavailableError (503) if DB is not ready.
    Auto-rollback on exception, auto-commit on success.
    """
    if not db_engine.is_ready:
        raise ServiceUnavailableError("Database is unavailable")

    async with db_engine.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**Key Design Decisions:**
- One session per request lifecycle, never shared across concurrent requests
- Session is committed on success, rolled back on any exception
- **DB readiness check before yielding** — if the engine reports not-ready, a 503 is raised immediately. This prevents database-dependent endpoints from returning false success during degraded mode.
- Connection pool defaults: pool_size=5, max_overflow=10
- `dispose()` has a 30-second timeout for graceful shutdown


### Module: Base ORM Model (`app/db/base.py`)

**Responsibility:** Declarative base with standard columns shared by all entities, plus a separate mixin for tenant-scoped entities.

```python
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Abstract declarative base. Not mapped to a table."""
    pass


class BaseModel(Base):
    """
    Abstract base providing common columns shared by ALL tables:
    - id: UUID PK (server-generated)
    - created_at: timestamptz (server default)
    - updated_at: timestamptz (server default, auto-update)
    - version: integer (optimistic concurrency)

    NOTE: tenant_id is NOT here. Use TenantScopedMixin for
    entities requiring tenant isolation.
    """
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    version: Mapped[int] = mapped_column(
        Integer,
        server_default="1",
        nullable=False,
    )


class TenantScopedMixin:
    """
    Mixin that adds tenant_id for entities requiring tenant isolation.

    Domain entities that need tenant scoping inherit from BOTH
    BaseModel and TenantScopedMixin:

        class Elder(BaseModel, TenantScopedMixin):
            __tablename__ = "elders"
            ...

    Tables like system configuration or audit logs may use only
    BaseModel without tenant_id.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
```

**Optimistic Concurrency Control:**

```python
from sqlalchemy.exc import StaleDataError


class OptimisticConcurrencyMixin:
    """Mixin providing version-check update logic."""

    @classmethod
    def apply_optimistic_update(
        cls, session: AsyncSession, instance, expected_version: int
    ) -> None:
        """
        Increment version and raise OptimisticConcurrencyError if
        current DB version != expected_version.
        """
        ...
```

**Tenant Immutability:**
- A SQLAlchemy `before_flush` event listener on `TenantScopedMixin` detects changes to `tenant_id` on dirty instances and raises `TenantImmutabilityError`.

**Key Design Decisions:**
- **BaseModel** contains ONLY shared fields: id, created_at, updated_at, version. These are common to ALL tables.
- **TenantScopedMixin** adds tenant_id (UUID, non-nullable, indexed) for entities that require tenant isolation.
- Domain entities that need tenant isolation inherit from BOTH BaseModel and TenantScopedMixin.
- The OutboxEntry model has its own tenant_id column (does NOT inherit from BaseModel) — it stays as-is.
- Tables like system configuration or audit logs may use only BaseModel without tenant_id.
- UUID primary keys generated server-side via `gen_random_uuid()` — no application-level UUID generation needed
- `version` field with explicit optimistic locking prevents lost updates
- `tenant_id` immutability enforced at ORM event level as a safety net
- All timestamps use `timezone=True` for consistent UTC handling


### Module: Authentication Abstractions (`app/middleware/auth.py`)

**Responsibility:** Define ActorContext, the pluggable authenticator interface, environment-guarded authenticator factory, and the FastAPI dependency for protected routes.

```python
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from fastapi import Request
from app.core.config import get_settings, AppEnv


@dataclass(frozen=True)
class ActorContext:
    """Immutable identity context derived from authentication."""
    actor_id: uuid.UUID
    actor_role: str
    tenant_id: uuid.UUID


class Authenticator(ABC):
    """Pluggable authenticator interface.

    Concrete implementations:
    - FakeAuthenticator (tests + explicit local dev)
    - CognitoAuthenticator (future production spec)
    """

    @abstractmethod
    async def authenticate(self, request: Request) -> ActorContext:
        """Extract and validate credentials, return ActorContext.

        Raises:
            AuthenticationError: if credentials are missing or invalid.
        """
        ...


class FakeAuthenticator(Authenticator):
    """Test/dev authenticator returning configurable ActorContext.

    Safety:
    - MAY be used in tests (always, via dependency override).
    - MAY be enabled in local development (APP_ENV=development)
      with explicit FAKE_AUTH_ENABLED=true config flag.
    - MUST NEVER be active in production.
    """

    def __init__(
        self,
        actor_id: uuid.UUID | None = None,
        actor_role: str = "care_worker",
        tenant_id: uuid.UUID | None = None,
    ) -> None:
        self._actor_id = actor_id or uuid.uuid4()
        self._actor_role = actor_role
        self._tenant_id = tenant_id or uuid.uuid4()

    async def authenticate(self, request: Request) -> ActorContext:
        return ActorContext(
            actor_id=self._actor_id,
            actor_role=self._actor_role,
            tenant_id=self._tenant_id,
        )
```

**Authenticator Factory (environment-guarded):**

```python
class NoAuthenticatorConfiguredError(Exception):
    """Raised at startup when production has no real authenticator."""
    pass


def get_authenticator() -> Authenticator:
    """Factory function for resolving the active authenticator.

    Rules:
    - In tests: FakeAuthenticator is injected via FastAPI dependency override.
      This function is never called directly in tests.
    - In development (APP_ENV=development) with FAKE_AUTH_ENABLED=true:
      Returns FakeAuthenticator for local dev convenience.
    - In production (APP_ENV=production):
      Returns the configured real authenticator.
      If no real authenticator is configured, raises
      NoAuthenticatorConfiguredError at startup — protected endpoints
      will fail closed (HTTP 401 for all requests).
    - NEVER defaults to FakeAuthenticator in production.
    """
    settings = get_settings()

    if settings.app_env == AppEnv.PRODUCTION:
        # In production: require a real authenticator or fail closed
        real_authenticator = _resolve_production_authenticator(settings)
        if real_authenticator is None:
            raise NoAuthenticatorConfiguredError(
                "No authenticator configured for production. "
                "Protected endpoints will reject all requests."
            )
        return real_authenticator

    # Development mode
    if settings.fake_auth_enabled:
        return FakeAuthenticator()

    # Development without fake auth — still require real config or fail
    real_authenticator = _resolve_production_authenticator(settings)
    if real_authenticator is None:
        raise NoAuthenticatorConfiguredError(
            "No authenticator configured. Set FAKE_AUTH_ENABLED=true "
            "for local development or configure a real authenticator."
        )
    return real_authenticator


def _resolve_production_authenticator(settings) -> Authenticator | None:
    """Resolve real authenticator from config. Returns None if not configured.

    Future: will return CognitoAuthenticator when that spec is implemented.
    """
    # Placeholder — no real authenticator in this foundation spec
    return None
```

**FastAPI Dependency:**

```python
from fastapi import Depends

async def get_actor_context(
    request: Request,
    authenticator: Authenticator = Depends(get_authenticator),
) -> ActorContext:
    """Resolve ActorContext for protected routes."""
    return await authenticator.authenticate(request)
```

**Key Design Decisions:**
- `ActorContext` is a frozen dataclass — immutable once created
- Actor identity derived exclusively from the authenticator; never from request body/query/headers
- Unprotected routes (health, ready) do not use the `get_actor_context` dependency
- **Environment safety**: `get_authenticator()` factory enforces that FakeAuthenticator is NEVER the production default
- In production without a real authenticator configured, protected endpoints fail closed (401)
- In tests, FakeAuthenticator is injected via `app.dependency_overrides[get_authenticator]` — the factory is bypassed entirely
- In development with explicit `FAKE_AUTH_ENABLED=true`, FakeAuthenticator is used for convenience


### Module: Tenant Scope and Repository Integration (`app/repositories/base.py`)

**Responsibility:** Enforce tenant-scoped queries via explicit tenant_id parameter. Contextvars are used for request-context propagation (correlation_id, actor context) but repositories receive tenant_id explicitly.

```python
from contextvars import ContextVar
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Request-scoped context for correlation_id and logging
_correlation_id: ContextVar[str] = ContextVar("_correlation_id", default="")


class BaseRepository:
    """Base repository enforcing tenant-scoped queries.

    Tenant_id is passed EXPLICITLY — not pulled from contextvars.
    This ensures:
    - Background jobs and message consumers can establish their own
      trusted context without relying on request-scoped contextvars.
    - SQL WHERE clauses always contain an explicit tenant predicate.
    - The calling service layer is responsible for passing the correct
      tenant_id from the authenticated ActorContext.
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        """
        Args:
            session: The async database session for this unit of work.
            tenant_id: The trusted tenant identifier from ActorContext.
                       All queries will be scoped to this tenant.
        """
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> UUID:
        """The tenant_id this repository is scoped to."""
        return self._tenant_id

    async def get_by_id(self, model_class, entity_id: UUID):
        """Fetch entity scoped to this repository's tenant.

        The SQL always includes: WHERE id = $1 AND tenant_id = $2
        """
        result = await self._session.execute(
            select(model_class).where(
                model_class.id == entity_id,
                model_class.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self, model_class, *, limit: int = 100, offset: int = 0):
        """List entities scoped to this repository's tenant."""
        result = await self._session.execute(
            select(model_class)
            .where(model_class.tenant_id == self._tenant_id)
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()
```

**Service Layer Usage Pattern:**

```python
class SomeService:
    """Example of how services use repositories with explicit tenant_id."""

    def __init__(self, session: AsyncSession, actor: ActorContext) -> None:
        self._session = session
        self._actor = actor
        # Repository is constructed with explicit tenant_id from ActorContext
        self._repo = BaseRepository(session, tenant_id=actor.tenant_id)

    async def get_item(self, item_id: UUID):
        return await self._repo.get_by_id(SomeModel, item_id)
```

**Background Job Context:**

```python
async def process_background_job(tenant_id: UUID, payload: dict) -> None:
    """Background jobs establish their own trusted context explicitly.

    They do NOT rely on request-scoped contextvars.
    """
    async with db_engine.session_factory() as session:
        repo = BaseRepository(session, tenant_id=tenant_id)
        # ... process with explicit tenant scope
```

**Key Design Decisions:**
- **Explicit tenant_id parameter** in repository constructor — not pulled from contextvars
- Contextvars remain for correlation_id propagation (middleware → handler flow) — this is fine for logging
- SQL WHERE clause always contains an explicit tenant predicate via the repository's `_tenant_id`
- Background jobs and message consumers establish their trusted context explicitly (they can't rely on request-scoped contextvars)
- The service layer is responsible for passing `actor.tenant_id` when constructing repositories
- `tenant_id` is never accepted from request body/params — only from `ActorContext`
- Test utilities construct repositories with explicit test tenant_id directly


### Module: Response Envelopes (`app/core/envelopes.py`)

**Responsibility:** Define standard success and error response structures.

```python
from pydantic import BaseModel, Field
from typing import Any, Generic, TypeVar
from datetime import datetime
from uuid import UUID

T = TypeVar("T")


class ResponseMeta(BaseModel):
    correlation_id: str
    timestamp: datetime


class SuccessEnvelope(BaseModel, Generic[T]):
    """Standard success response wrapper."""
    data: T
    meta: ResponseMeta


class ValidationDetail(BaseModel):
    field: str
    reason: str


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str
    details: list[ValidationDetail] | None = None


class ErrorEnvelope(BaseModel):
    """Standard error response wrapper."""
    error: ErrorBody
```

### Module: Structured Error Handling (`app/core/exceptions.py`)

**Responsibility:** Define domain exception hierarchy and exception-to-envelope mapping.

```python
class DomainException(Exception):
    """Base for all domain-specific exceptions."""
    pass


class NotFoundError(DomainException):
    """Entity not found or access denied (returns 404)."""
    pass


class ConflictError(DomainException):
    """Concurrent modification or duplicate (returns 409)."""
    pass


class ValidationError(DomainException):
    """Input validation failure (returns 422)."""
    def __init__(self, details: list[dict]):
        self.details = details


class AuthorizationDeniedError(DomainException):
    """Access denied — mapped to 404 to hide resource existence."""
    pass


class AuthenticationError(DomainException):
    """Authentication failure (returns 401)."""
    pass


class ServiceUnavailableError(DomainException):
    """Service dependency unavailable (returns 503)."""
    pass


class TenantScopeError(DomainException):
    """Missing or invalid tenant context."""
    pass


class OptimisticConcurrencyError(ConflictError):
    """Stale version on update (returns 409)."""
    pass


class TenantImmutabilityError(DomainException):
    """Attempt to modify tenant_id after creation."""
    pass
```

**Exception Handler Registration:**

```python
# In app/main.py or dedicated error handler module
EXCEPTION_MAP = {
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 422,
    AuthorizationDeniedError: 404,  # Hide resource existence
    AuthenticationError: 401,
    ServiceUnavailableError: 503,
    TenantScopeError: 401,
}
```

**Key Design Decisions:**
- `AuthorizationDeniedError` maps to 404 (not 403) to prevent resource enumeration
- `ServiceUnavailableError` maps to 503 for degraded-mode responses
- All unhandled exceptions produce 500 with only `correlation_id` and generic code
- In production, stack traces, SQL, and internal paths are never exposed
- Error handler has its own try/except — if it fails, returns a minimal 500


### Module: Request Logger (`app/middleware/logging.py`)

**Responsibility:** Structured JSON logging for every HTTP request with correlation_id propagation.

```python
import uuid
import time
import logging
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key"}


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Log structured JSON for every request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract or generate correlation_id
        correlation_id = request.headers.get(
            "x-correlation-id", str(uuid.uuid4())
        )
        _correlation_id.set(correlation_id)

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        log_entry = {
            "timestamp": ...,  # ISO 8601
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "correlation_id": correlation_id,
        }

        # Include actor/tenant on 4xx/5xx for auditing
        if response.status_code >= 400:
            log_entry["tenant_id"] = ...  # from context if available
            log_entry["actor_id"] = ...   # from context if available

        logger.info("request_completed", extra=log_entry)

        # Attach correlation_id to response headers
        response.headers["x-correlation-id"] = correlation_id
        return response
```

**Key Design Decisions:**
- Correlation ID from `x-correlation-id` header, or auto-generated UUID v4
- Uses `contextvars` so all downstream log calls include the correlation_id
- Never logs request/response bodies, auth headers, cookies, or sensitive query params
- Duration measured with `time.perf_counter()` for millisecond precision
- Log emission failure does not interrupt request processing


### Module: Health & Readiness Endpoints (`app/api/health.py`, `app/api/ready.py`)

**Responsibility:** Operational endpoints for orchestrators and load balancers.

```python
# app/api/health.py
from fastapi import APIRouter
import time

router = APIRouter()
_start_time = time.time()


@router.get("/health")
async def health():
    """Process liveness check.

    Always returns 200 while the process is alive.
    DOES NOT access the database — no DB dependency whatsoever.
    """
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - _start_time),
    }


# app/api/ready.py
@router.get("/ready")
async def ready(db_engine: DatabaseEngine = Depends(get_db_engine)):
    """Readiness check. Verifies DB connectivity.

    Returns 503 when database connectivity is unavailable.
    """
    try:
        connected = await asyncio.wait_for(
            db_engine.check_connectivity(), timeout=3.0
        )
        if connected:
            return {"status": "ready", "database": "connected"}
    except (asyncio.TimeoutError, Exception):
        pass

    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "database": "unavailable"},
    )
```

**Key Design Decisions:**
- **Health endpoint**: no dependencies, responds immediately, includes uptime. NEVER touches DB.
- **Readiness endpoint**: 3-second timeout on DB check, returns 503 if unavailable
- Both are unprotected (no auth required)
- Non-GET methods return 405 (handled by FastAPI's default method routing)
- Database-dependent endpoints (any route using `get_db_session`) receive 503 automatically if DB is unavailable via the session dependency guard


### Module: Transactional Outbox (`app/models/outbox.py`, `app/events/`)

**Responsibility:** Persist domain events atomically alongside entity changes within the same database transaction. The outbox is the **write-path** only — a separate relay process (out of this spec's scope) reads committed outbox records and publishes them.

#### Write-Path vs Relay-Path Distinction

```mermaid
sequenceDiagram
    participant S as Service
    participant DB as PostgreSQL
    participant OW as Outbox Writer
    participant Relay as Relay Process (future)
    participant Bus as EventBridge (future)

    S->>DB: BEGIN transaction
    S->>DB: INSERT/UPDATE domain entity
    S->>OW: write_outbox_entry(session, ...)
    OW->>DB: INSERT INTO outbox (same transaction)
    S->>DB: COMMIT (entity + outbox atomically)
    Note over DB: Transaction committed. Both entity and outbox entry visible.

    Note over Relay: Separate process (OUT OF SCOPE)
    Relay->>DB: SELECT * FROM outbox WHERE published = false
    Relay->>Bus: Publish event
    Relay->>DB: UPDATE outbox SET published = true
```

**Key Behaviors:**
- Domain entity persistence and outbox insertion occur in the **same database transaction**. They are committed together.
- **Publishing does NOT occur inside the API business transaction.** The API transaction writes to the outbox table and commits. A separate relay process (out of this spec's scope) reads committed outbox records and publishes them.
- Publisher failure leaves records in `published=false` state, making them retryable.
- **No EventBridge or SQS integration** is included in this spec.

```python
# app/models/outbox.py
from app.db.base import Base
import uuid
from sqlalchemy import String, Boolean, JSON, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class OutboxEntry(Base):
    """Domain event persisted for reliable relay.

    NOTE: Inherits from Base (DeclarativeBase), NOT BaseModel.
    Has its own tenant_id column directly.
    """
    __tablename__ = "outbox"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )

    __table_args__ = (
        Index("ix_outbox_unpublished", "published", "created_at"),
    )
```

```python
# app/events/outbox_writer.py
import json
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert


MAX_PAYLOAD_BYTES = 256 * 1024  # 256 KB


async def write_outbox_entry(
    session: AsyncSession,
    event_type: str,
    aggregate_id: uuid.UUID,
    tenant_id: uuid.UUID,
    payload: dict,
    event_id: uuid.UUID | None = None,
) -> None:
    """Write event to outbox within the current transaction.

    This is the WRITE-PATH of the transactional outbox pattern.
    The outbox entry is written in the SAME transaction as the
    domain entity change — committed together, rolled back together.

    A separate relay process (out of scope) will later read committed
    entries and publish them to EventBridge/SQS.

    - Validates payload size (max 256 KB)
    - Uses INSERT ... ON CONFLICT DO NOTHING for idempotency
    - event_id auto-generated if not provided
    """
    if event_id is None:
        event_id = uuid.uuid4()

    payload_bytes = json.dumps(payload).encode("utf-8")
    if len(payload_bytes) > MAX_PAYLOAD_BYTES:
        raise ValidationError(
            [{"field": "payload", "reason": f"Payload exceeds {MAX_PAYLOAD_BYTES} bytes"}]
        )

    stmt = insert(OutboxEntry).values(
        event_id=event_id,
        event_type=event_type,
        aggregate_id=aggregate_id,
        tenant_id=tenant_id,
        payload=payload,
    ).on_conflict_do_nothing(index_elements=["event_id"])

    await session.execute(stmt)
```

```python
# app/events/publisher.py
from abc import ABC, abstractmethod
from uuid import UUID


class EventPublisher(ABC):
    """Abstract interface for the relay's publishing contract.

    This represents what a relay process does: reads committed outbox
    records and publishes them to an external bus. The relay is OUT OF
    SCOPE for this foundation spec.
    """

    @abstractmethod
    async def publish(
        self,
        event_type: str,
        aggregate_id: UUID,
        tenant_id: UUID,
        payload: dict,
    ) -> None:
        ...


class FakePublisher(EventPublisher):
    """In-memory publisher for testing the outbox_writer behavior.

    Simulates what a relay would do — collects events for test assertions.
    Does NOT represent the API write-path (that's outbox_writer).
    """

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(
        self,
        event_type: str,
        aggregate_id: UUID,
        tenant_id: UUID,
        payload: dict,
    ) -> None:
        self.events.append({
            "event_type": event_type,
            "aggregate_id": aggregate_id,
            "tenant_id": tenant_id,
            "payload": payload,
        })
```

**Key Design Decisions:**
- Outbox written in same transaction as entity change (atomicity guaranteed by DB)
- Rollback of entity transaction automatically rolls back outbox entry
- **Publishing does NOT happen in the API transaction** — a separate relay (future spec) handles that
- Idempotent writes via `ON CONFLICT DO NOTHING` on `event_id`
- Payload size validated before persistence (max 256 KB)
- `FakePublisher` simulates what a relay would do — for testing outbox_writer behavior
- Index on `(published, created_at)` supports efficient relay polling
- `EventPublisher` ABC represents the relay's contract, not the API write-path


### Module: Application Entrypoint (`app/main.py`)

**Responsibility:** FastAPI app creation, lifespan management, component initialization in defined order.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import get_settings, AppEnv


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ordered startup and shutdown."""
    settings = get_settings()

    # Startup order: Settings → Engine → Middleware → Routes
    db_engine = DatabaseEngine(settings)

    # Attempt DB connectivity (non-fatal — degraded mode)
    try:
        await db_engine.check_connectivity()
    except Exception as e:
        logger.error("db_startup_failed", component="DatabaseEngine", exc=e)
        # db_engine.is_ready remains False → session dependency will 503

    app.state.db_engine = db_engine
    app.state.settings = settings

    logger.info(
        "app_ready",
        host=settings.host,
        port=settings.port,
    )

    yield

    # Shutdown: reverse order
    await db_engine.dispose(timeout=30.0)


def create_app() -> FastAPI:
    settings = get_settings()

    docs_url = settings.docs_url if settings.app_env == AppEnv.DEVELOPMENT else None
    openapi_url = "/openapi.json" if settings.app_env == AppEnv.DEVELOPMENT else None

    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        docs_url=docs_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    # Register middleware (order matters: outermost first)
    app.add_middleware(RequestLoggerMiddleware)

    # Register routes
    app.include_router(health_router)
    app.include_router(ready_router)

    # Register exception handlers
    register_exception_handlers(app)

    return app


app = create_app()
```

**Key Design Decisions:**
- Uses FastAPI's `lifespan` context manager (modern pattern, not `on_event`)
- Startup failure in DB = degraded mode (app runs, health=200, ready=503, DB routes=503)
- Fatal startup failure (e.g., config invalid) = process exits non-zero within 10s
- Shutdown disposes in reverse order with 30s overall timeout
- OpenAPI docs disabled in production (404 for /docs, /redoc, /openapi.json)


### Module: Alembic Async Configuration (`alembic/env.py`)

**Responsibility:** Configure Alembic for async SQLAlchemy with asyncpg.

```python
# alembic/env.py
import asyncio
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings
from app.db.base import Base
# Import all models to register metadata
from app.models import outbox  # noqa: F401


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL generation)."""
    url = get_settings().database_url
    context.configure(url=url, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using async engine."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())
```

**Key Design Decisions:**
- Alembic env.py uses async engine matching application's connection scheme
- Metadata from `Base` covers all models registered via imports
- `autogenerate` works by comparing live DB schema against registered metadata
- Connection string sourced from `Settings_Manager` (same config path as app)


### Module: Docker Compose (`docker-compose.yml`)

**Responsibility:** Local development environment with PostgreSQL 16.

```yaml
version: "3.8"

services:
  postgres:
    image: postgres:16
    container_name: kinsun-postgres
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-kinsun}
      POSTGRES_USER: ${POSTGRES_USER:-kinsun}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-kinsun_dev}
    ports:
      - "5432:5432"
    volumes:
      - kinsun_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-kinsun}"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 30s

volumes:
  kinsun_pgdata:
    name: kinsun_pgdata
```

**Key Design Decisions:**
- Named volume `kinsun_pgdata` persists data across container restarts
- Environment variables have defaults, overridable via `.env` file
- `pg_isready` healthcheck with 5s interval and 30s start_period
- Single service for now; future specs may add Redis, LocalStack, etc.


### Module: Testing Infrastructure

**Responsibility:** pytest configuration, fixtures for unit and integration tests, database isolation.

#### pytest configuration (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
testpaths = ["tests/unit", "tests/integration"]
asyncio_mode = "auto"
```

#### Integration Test Fixtures (`tests/integration/conftest.py`)

```python
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import get_settings
from app.db.base import Base


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create engine connected to Test_Database."""
    settings = get_settings()
    engine = create_async_engine(settings.test_database_url)
    # Run migrations to create schema
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncSession:
    """Per-test session with transaction rollback for isolation."""
    async with test_engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await transaction.rollback()


@pytest.fixture
async def committed_session(test_engine) -> AsyncSession:
    """Session that commits — for tests needing visible data.
    Performs explicit cleanup after test.
    """
    session = async_sessionmaker(test_engine)()
    yield session
    # Cleanup: truncate tables or delete test data
    await session.close()
```

**Key Design Decisions:**
- Default test isolation: transaction rollback (no residual data)
- `committed_session` fixture for tests needing cross-connection visibility
- Alembic migrations run as session-scoped setup (schema created once)
- Unit tests have no DB fixtures — they run without any external dependencies
- `TEST_DATABASE_URL` environment variable isolates test DB from dev/prod


## Data Models

### SQLAlchemy Models

| Model | Table | Columns | Notes |
|-------|-------|---------|-------|
| `BaseModel` | (abstract) | id (UUID PK), created_at (timestamptz), updated_at (timestamptz), version (int) | Inherited by ALL entities. Contains only shared fields. |
| `TenantScopedMixin` | (mixin) | tenant_id (UUID, non-nullable, indexed) | Added to entities requiring tenant isolation. Combined with BaseModel. |
| `OutboxEntry` | `outbox` | event_id (UUID PK), event_type (varchar 255), aggregate_id (UUID), tenant_id (UUID), payload (JSON), created_at (timestamptz), published (bool) | Inherits from Base (DeclarativeBase) directly. Own tenant_id column. |

### Inheritance Patterns

```python
# Entity WITH tenant isolation (most domain entities):
class Elder(BaseModel, TenantScopedMixin):
    __tablename__ = "elders"
    # Has: id, created_at, updated_at, version, tenant_id
    ...

# Entity WITHOUT tenant isolation (system-level tables):
class SystemConfig(BaseModel):
    __tablename__ = "system_config"
    # Has: id, created_at, updated_at, version
    # Does NOT have tenant_id
    ...

# Outbox (its own structure, not BaseModel):
class OutboxEntry(Base):
    __tablename__ = "outbox"
    # Has: event_id (PK), event_type, aggregate_id, tenant_id, payload, created_at, published
    ...
```

### Pydantic Schemas

| Schema | Purpose | Fields |
|--------|---------|--------|
| `Settings` | App configuration | app_env, app_title, app_version, docs_url, host, port, database_url, db_pool_size, db_max_overflow, test_database_url, database_password, fake_auth_enabled |
| `SuccessEnvelope[T]` | API success response | data: T, meta: ResponseMeta |
| `ErrorEnvelope` | API error response | error: ErrorBody |
| `ErrorBody` | Error details | code, message, correlation_id, details? |
| `ValidationDetail` | Field-level error | field, reason |
| `ResponseMeta` | Response metadata | correlation_id, timestamp |
| `ActorContext` | Auth identity | actor_id (UUID), actor_role (str), tenant_id (UUID) |

### Database Schema (Initial Migration)

```sql
-- outbox table
CREATE TABLE outbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(255) NOT NULL,
    aggregate_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX ix_outbox_unpublished ON outbox (published, created_at)
    WHERE published = FALSE;
```

### Configuration Schema

```
APP_ENV=development|production     (default: development)
APP_TITLE=kinsun.ai Core API      (default)
APP_VERSION=0.1.0                  (default)
DOCS_URL=/docs                     (default)
HOST=0.0.0.0                       (default)
PORT=8000                          (1-65535, default: 8000)
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db  (required)
DB_POOL_SIZE=5                     (>= 1, default: 5)
DB_MAX_OVERFLOW=10                 (>= 0, default: 10)
TEST_DATABASE_URL=postgresql+asyncpg://...  (required for integration tests)
FAKE_AUTH_ENABLED=false            (default: false, only honored in development)
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Mandatory Properties (Must Pass for Foundation)

These 6 properties are the mandatory correctness guarantees for this foundation. They must be implemented as property-based tests and pass before the foundation is considered complete.

### Property 1: Identifier and timestamp invariants

*For any* entity persisted through the ORM (whether tenant-scoped or not), the following invariants SHALL hold: (a) the `id` field is a valid UUID v4, (b) `created_at` is populated with a non-null timestamp, (c) `updated_at` is populated with a non-null timestamp, and (d) `created_at <= updated_at`.

**Validates: Requirements 4.1, 4.3**

### Property 2: Tenant-scope non-expansion

*For any* query executed through a `BaseRepository` constructed with `tenant_id=X`, the result set SHALL never contain a row where `tenant_id != X`. This holds regardless of what data exists in the database for other tenants.

**Validates: Requirements 4.7, 12.2**

### Property 3: Optimistic version monotonicity

*For any* entity with current database version V, an update providing `expected_version = V` SHALL succeed and result in `version = V + 1`. An update providing `expected_version != V` SHALL be rejected with `OptimisticConcurrencyError`. The version value SHALL increase by exactly 1 on each successful update.

**Validates: Requirements 4.5**

### Property 4: Transaction rollback guarantee

*For any* service operation that raises an exception after beginning database modifications within a session, the session SHALL be rolled back and no partial writes SHALL persist in the database.

**Validates: Requirements 3.6**

### Property 5: Outbox atomicity

*For any* database transaction that writes both a domain entity change and an outbox entry, if the transaction is committed then both the entity change and the outbox entry SHALL be visible. If the transaction is rolled back, neither the entity change nor the outbox entry SHALL be persisted.

**Validates: Requirements 13.3, 13.4**

### Property 6: Outbox duplicate prevention

*For any* `event_id`, writing an outbox entry with that `event_id` a second time SHALL result in exactly one row in the outbox table and SHALL NOT raise an error on the second write.

**Validates: Requirements 13.7**

### Future Hardening Properties (Recommended, Not Mandatory)

The following properties are recommended for implementation as the system matures. They are documented here for traceability but are NOT required to pass for the foundation to be considered complete.

#### Future Property A: Invalid configuration rejection

*For any* configuration input that violates a declared type constraint, contains a value outside its valid range (e.g., port not in 1–65535), or is missing a required field, the Settings_Manager SHALL raise a validation error and prevent application startup.

**Validates: Requirements 2.3**

#### Future Property B: Secret field redaction

*For any* Settings field whose name contains "password", "secret", or "key", calling `__repr__`, `__str__`, or `model_dump` SHALL produce output where that field's value is replaced with "***" and the actual secret value does not appear.

**Validates: Requirements 2.6**

#### Future Property C: Database URL scheme validation

*For any* DATABASE_URL string that does not begin with `postgresql+asyncpg://`, the Settings_Manager SHALL reject it with a validation error. *For any* DATABASE_URL string that does begin with `postgresql+asyncpg://`, the scheme validation SHALL pass.

**Validates: Requirements 2.8**

#### Future Property D: Correlation ID generation

*For any* HTTP request that does not include an `x-correlation-id` header, the system SHALL generate a valid UUID v4 string and attach it as the correlation_id in both the response header and log entry.

**Validates: Requirements 10.2**

#### Future Property E: Sensitive data exclusion from logs

*For any* log entry emitted by the Request_Logger, the entry SHALL not contain authorization header values, cookie values, request body content, or response body content.

**Validates: Requirements 10.3**

#### Future Property F: Identity derived exclusively from authenticator

*For any* HTTP request to a protected route — regardless of actor_id, actor_role, or tenant_id values present in the request body, query parameters, or headers — the resolved ActorContext SHALL equal the authenticator's return value, not any request-supplied values.

**Validates: Requirements 11.6, 12.3**

#### Future Property G: Exception-to-envelope mapping

*For any* unhandled exception, the error response SHALL contain a valid UUID v4 correlation_id, a non-empty error code string, and a non-empty message string. *For any* domain exception in the exception map, the HTTP status code SHALL match: NotFoundError→404, ConflictError→409, ValidationError→422, AuthorizationDeniedError→404.

**Validates: Requirements 9.1, 9.2, 9.3**

#### Future Property H: Production error response safety

*For any* error response produced while APP_ENV=production, the serialized JSON SHALL not contain stack trace patterns, internal file paths, SQL query text, or database object names.

**Validates: Requirements 8.6**

#### Future Property I: Validation error details completeness

*For any* validation error with N field failures, the error envelope's "details" array SHALL contain exactly N entries, each with a non-empty "field" and a non-empty "reason" string.

**Validates: Requirements 8.3**

#### Future Property J: Tenant ID immutability

*For any* persisted tenant-scoped entity, attempting to modify the tenant_id field SHALL raise a TenantImmutabilityError regardless of the new tenant_id value, preserving the original tenant_id.

**Validates: Requirements 4.6**

#### Future Property K: Migration round-trip consistency

*For any* migration chain, executing upgrade to head, then downgrade by one step, then upgrade to head again SHALL produce the same alembic_version table state as a single upgrade to head from empty.

**Validates: Requirements 17.3**


## Error Handling

### Exception Hierarchy

```
DomainException (base)
├── NotFoundError              → HTTP 404
├── ConflictError              → HTTP 409
│   └── OptimisticConcurrencyError → HTTP 409
├── ValidationError            → HTTP 422 (with details array)
├── AuthorizationDeniedError   → HTTP 404 (hides resource existence)
├── AuthenticationError        → HTTP 401
├── ServiceUnavailableError    → HTTP 503 (degraded mode)
├── TenantScopeError           → HTTP 401
└── TenantImmutabilityError    → HTTP 500 (internal bug, should never reach API)
```

### Error Handling Strategy

1. **Domain exceptions** — mapped to appropriate HTTP status via `EXCEPTION_MAP`
2. **Pydantic ValidationError** — caught and converted to 422 with field-level details
3. **SQLAlchemy StaleDataError** — caught and converted to `OptimisticConcurrencyError` (409)
4. **ServiceUnavailableError** — returned as 503 during degraded mode (DB unavailable)
5. **Unhandled exceptions** — caught by global handler, return 500 with generic message
6. **Error handler failure** — innermost try/except returns minimal 500 with correlation_id only

### Production vs Development Error Responses

| Field | Development | Production |
|-------|-------------|------------|
| code | Yes | Yes |
| message | Detailed (may include class name) | Generic ("Internal server error") |
| correlation_id | Yes | Yes |
| details | Yes (for 422) | Yes (for 422) |
| stack_trace | Included in logs only | Never |
| sql/paths | In logs only | Never |

### Error Flow

```mermaid
flowchart TD
    E[Exception Raised] --> D{Domain Exception?}
    D -->|Yes| M[Map to HTTP status]
    D -->|No| P{Pydantic Error?}
    P -->|Yes| V[422 + field details]
    P -->|No| S{StaleDataError?}
    S -->|Yes| C[409 Conflict]
    S -->|No| SU{ServiceUnavailable?}
    SU -->|Yes| SV[503 Service Unavailable]
    SU -->|No| G[500 Generic]
    M --> ENV[Build error envelope]
    V --> ENV
    C --> ENV
    SV --> ENV
    G --> ENV
    ENV --> PROD{Production?}
    PROD -->|Yes| REDACT[Redact internals]
    PROD -->|No| FULL[Include debug info in logs]
    REDACT --> RESP[Return ErrorEnvelope]
    FULL --> RESP
```


## Testing Strategy

### Dual Testing Approach

This feature uses both **unit tests** (specific examples, edge cases) and **property-based tests** (universal properties across generated inputs).

### Property-Based Testing Configuration

- **Library:** [hypothesis](https://hypothesis.readthedocs.io/) (Python's standard PBT library)
- **Minimum iterations:** 100 per property test
- **Tag format:** `# Feature: core-api-foundation, Property {N}: {title}`
- **Mandatory scope:** Only the 6 mandatory properties (Properties 1–6) MUST be implemented and pass
- **Future hardening:** Properties A–K are recommended but not required for foundation completion

Each mandatory correctness property will be implemented as a single property-based test using Hypothesis. Properties 1–3 test pure logic or in-memory behavior. Properties 4–6 involve database interactions and will use PBT with the test database (wrapped in transaction rollback fixtures).

### Test Organization

```
tests/
├── unit/
│   ├── test_config.py              # Settings validation
│   ├── test_envelopes.py           # Response envelope structure
│   ├── test_error_handling.py      # Exception mapping
│   ├── test_auth.py                # ActorContext, authenticator factory, env guards
│   ├── test_tenant_scope.py        # Tenant scoping logic
│   ├── test_logging.py             # Request logger
│   └── test_outbox_validation.py   # Payload validation
└── integration/
    ├── test_health.py              # GET /health endpoint
    ├── test_ready.py               # GET /ready endpoint (200 and 503 cases)
    ├── test_degraded_mode.py       # DB-dependent endpoints return 503
    ├── test_db_session.py          # Session lifecycle (Property 4)
    ├── test_optimistic_concurrency.py  # Version control (Property 3)
    ├── test_outbox.py              # Atomicity, idempotency (Properties 5, 6)
    ├── test_tenant_isolation.py    # Cross-tenant query prevention (Property 2)
    ├── test_base_model.py          # UUID/timestamp invariants (Property 1)
    └── test_migrations.py          # Upgrade/downgrade
```

### Unit Test Focus

- **Specific examples:** health/ready response structure, settings singleton behavior, env profile selection
- **Edge cases:** error handler self-failure, log emission failure, null tenant_id on protected route
- **Interface contracts:** Authenticator ABC, EventPublisher ABC, FakePublisher behavior
- **Environment guards:** `get_authenticator()` factory behavior in development vs production, FakeAuthenticator never active in production

### Integration Test Focus

- Database session lifecycle (connect, query, commit/rollback)
- Optimistic concurrency with real DB (version increment, stale rejection)
- Outbox atomicity (commit includes outbox, rollback excludes outbox)
- Outbox idempotency (duplicate event_id produces one row, no error)
- Tenant isolation (query with tenant_id=X never returns tenant_id!=X)
- UUID and timestamp invariants on persisted entities
- Migration upgrade/downgrade/upgrade round-trip
- Health and readiness endpoints (with and without DB connectivity)
- Degraded mode: DB-dependent endpoints return 503 when DB is unavailable
- Full request flow through middleware stack

### Mandatory Property-Based Test Examples

```python
from hypothesis import given, settings
from hypothesis.strategies import uuids, integers, lists, builds
import uuid


@settings(max_examples=100)
@given(tenant_a=uuids(), tenant_b=uuids())
def test_tenant_scope_non_expansion(tenant_a, tenant_b, db_session):
    """Feature: core-api-foundation, Property 2: Tenant-scope non-expansion

    For any query with tenant_id=A, no row with tenant_id=B (B!=A) is returned.
    """
    # Insert rows for both tenants
    # Query via BaseRepository(session, tenant_id=tenant_a)
    # Assert all results have tenant_id == tenant_a
    ...


@settings(max_examples=100)
@given(current_version=integers(min_value=1, max_value=10000),
       expected_version=integers(min_value=1, max_value=10000))
def test_optimistic_version_monotonicity(current_version, expected_version, db_session):
    """Feature: core-api-foundation, Property 3: Optimistic version monotonicity

    If expected == current → success, new version = current + 1
    If expected != current → OptimisticConcurrencyError
    """
    ...


@settings(max_examples=100)
@given(event_id=uuids())
def test_outbox_duplicate_prevention(event_id, committed_session):
    """Feature: core-api-foundation, Property 6: Outbox duplicate prevention

    Writing the same event_id twice → exactly one row, no error.
    """
    ...
```

### Test Dependencies

```toml
[project.optional-dependencies]
test = [
    "pytest==8.3.4",
    "pytest-asyncio==0.24.0",
    "hypothesis==6.118.0",
    "httpx==0.27.2",
    "pytest-cov==6.0.0",
]
```
