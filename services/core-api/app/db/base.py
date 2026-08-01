"""Base ORM models and mixins for the Core API.

Provides:
- Base: SQLAlchemy DeclarativeBase bound to the eldercare_ai schema
- BaseModel: Abstract base with id, created_at, updated_at
- VersionedMixin: Adds the version column (only some tables have it)
- TenantScopedMixin: Adds tenant_id for entities requiring tenant isolation
- OptimisticConcurrencyMixin: Version-check update logic
- before_flush event listener enforcing tenant_id immutability

Schema mapping
--------------
Tables live in the `eldercare_ai` schema created by the Alembic baseline
(revision f393b4452ce8), not in `public`. That schema names each primary key
after its table — `actor.actor_id`, `elder.elder_id` — rather than a uniform
`id`. Instead of renaming the attribute everywhere, each model declares
`__pk_name__` and BaseModel maps the Python attribute `id` onto that column.
Application code keeps using `instance.id` and `Model.id`.

`version` is NOT universal in the baseline — only care_assignment carries it —
so it is an opt-in mixin rather than part of BaseModel.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, Integer, MetaData, event, inspect, update
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, declared_attr, mapped_column
from sqlalchemy.sql import func

from app.core.exceptions import OptimisticConcurrencyError, TenantImmutabilityError

#: PostgreSQL schema holding every domain table (see the Alembic baseline).
SCHEMA_NAME = "eldercare_ai"


def pg_enum(name: str, *values: str) -> ENUM:
    """Reference an existing PostgreSQL ENUM type in the eldercare_ai schema.

    `create_type=False` is essential: the types already exist because the
    baseline migration created them. Without it SQLAlchemy would emit
    CREATE TYPE and fail on a second run.

    Args:
        name: The PostgreSQL type name, e.g. "actor_type_enum".
        *values: The type's labels, used for client-side validation only.

    Returns:
        An ENUM type bound to the eldercare_ai schema.
    """
    return ENUM(*values, name=name, schema=SCHEMA_NAME, create_type=False)


class Base(DeclarativeBase):
    """Abstract declarative base. Not mapped to a table."""

    metadata = MetaData(schema=SCHEMA_NAME)


class BaseModel(Base):
    """Abstract base providing common columns shared by ALL tables.

    Columns:
    - id: UUID PK mapped onto the table's own PK column (see __pk_name__)
    - created_at: timestamptz (server default now)
    - updated_at: timestamptz (server default now, auto-update on modification)

    NOTE: tenant_id is NOT here. Use TenantScopedMixin for entities requiring
    tenant isolation, and VersionedMixin for tables that carry `version`.
    """

    __abstract__ = True

    #: Name of this table's primary key column in the eldercare_ai schema.
    __pk_name__: ClassVar[str]

    @declared_attr
    def id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        """Map the `id` attribute onto the table's own primary key column."""
        return mapped_column(
            cls.__pk_name__,
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


class VersionedMixin:
    """Adds the optimistic-concurrency `version` column.

    Only tables that actually declare `version` in the baseline may use this.
    """

    version: Mapped[int] = mapped_column(
        Integer,
        server_default="1",
        nullable=False,
    )


class TenantScopedMixin:
    """Mixin that adds tenant_id for entities requiring tenant isolation.

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
    )


class OptimisticConcurrencyMixin:
    """Mixin providing version-check update logic.

    Uses a WHERE version = expected_version clause on UPDATE.
    If no rows are affected (version mismatch), raises
    OptimisticConcurrencyError.
    """

    @classmethod
    async def apply_optimistic_update(
        cls,
        session: AsyncSession,
        instance: BaseModel,
        expected_version: int,
    ) -> None:
        """Increment version and raise OptimisticConcurrencyError if stale.

        Executes an UPDATE with WHERE id = :id AND version = :expected_version,
        setting version = expected_version + 1. If no rows match (stale version),
        raises OptimisticConcurrencyError.

        Args:
            session: The async database session.
            instance: The ORM instance to update.
            expected_version: The version the caller expects is current in the DB.

        Raises:
            OptimisticConcurrencyError: If the current DB version does not match
                expected_version (stale data).
        """
        model_class = type(instance)
        stmt = (
            update(model_class)
            .where(
                model_class.id == instance.id,
                model_class.version == expected_version,
            )
            .values(version=expected_version + 1)
            .execution_options(synchronize_session="fetch")
        )
        result = await session.execute(stmt)

        if result.rowcount == 0:
            raise OptimisticConcurrencyError(
                f"Optimistic concurrency conflict: expected version {expected_version} "
                f"for {model_class.__name__} with id {instance.id}"
            )

        # Update the in-memory instance to reflect the new version
        instance.version = expected_version + 1


def _check_tenant_immutability(session, flush_context, instances) -> None:  # noqa: ARG001
    """before_flush event listener that prevents tenant_id modification.

    Inspects all dirty instances that use TenantScopedMixin. If tenant_id
    has been changed, raises TenantImmutabilityError.
    """
    for instance in session.dirty:
        if not isinstance(instance, TenantScopedMixin):
            continue

        state = inspect(instance)
        history = state.attrs.tenant_id.history

        # history.deleted contains old values if the attribute was changed
        if history.deleted:
            raise TenantImmutabilityError(
                f"Cannot modify tenant_id on {type(instance).__name__} "
                f"(id={getattr(instance, 'id', 'unknown')}). "
                f"tenant_id is immutable after creation."
            )


# Register the before_flush event listener on the sync Session class.
# AsyncSession delegates flush operations to the underlying sync Session,
# so the event fires correctly for both sync and async usage.
event.listen(Session, "before_flush", _check_tenant_immutability)
