"""Driver-aware normalization for the shared PostgreSQL connection URL."""

from __future__ import annotations

from sqlalchemy.engine import make_url


def to_psycopg_database_url(database_url: str) -> str:
    """Convert the Core asyncpg URL into an Alembic-compatible psycopg URL.

    asyncpg names its TLS query option ``ssl`` while psycopg/libpq expects
    ``sslmode``. Keeping that distinction here lets local Alembic commands and
    the asynchronous Core runtime safely share one credential-bearing URL.
    """
    url = make_url(database_url)
    if url.drivername not in {
        "postgresql",
        "postgresql+asyncpg",
        "postgresql+psycopg",
    }:
        raise ValueError("DATABASE_URL must use a supported PostgreSQL driver")

    query = dict(url.query)
    asyncpg_ssl = query.pop("ssl", None)
    psycopg_ssl = query.get("sslmode")
    if asyncpg_ssl is not None:
        if psycopg_ssl is not None and psycopg_ssl != asyncpg_ssl:
            raise ValueError("DATABASE_URL contains conflicting TLS modes")
        query["sslmode"] = asyncpg_ssl

    normalized = url.set(drivername="postgresql+psycopg", query=query)
    return normalized.render_as_string(hide_password=False)
