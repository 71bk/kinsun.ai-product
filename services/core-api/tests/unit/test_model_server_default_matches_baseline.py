"""A model's server_default must match the frozen baseline, in both directions.

``server_default`` is not decoration: it is what decides whether SQLAlchemy puts
an unset column into the INSERT at all. Both ways of getting it wrong end in the
same NOT NULL violation, raised at INSERT time in whichever code path reached
the table first -- never at validation time.

  model claims a default the baseline lacks
      SQLAlchemy omits the column, trusting PostgreSQL to fill it. PostgreSQL
      has nothing to fill it with, so the row goes in as NULL.

  baseline has a default the model does not claim
      SQLAlchemy sends an explicit NULL rather than omitting the column, so the
      database default never gets the chance to apply.

This test deliberately needs no database. The drift it catches otherwise
surfaces only in ``tests/integration``, which per AGENTS.md 10 runs in CI alone,
so without a check at this level it cannot be caught before pushing.

Scope: tables created by the baseline. That snapshot is frozen and SHA-256
verified (ADR 0002), so parsing it is stable. Tables added by later migrations
are not covered here.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from pathlib import Path

import app.models
from app.db.base import BaseModel

BASELINE_SQL = next(
    (Path(__file__).resolve().parents[2] / "alembic" / "versions" / "sql").glob("*.sql")
)

_CREATE_TABLE = re.compile(
    r"CREATE TABLE eldercare_ai\.(\w+)\s*\((.*?)\n\);",
    re.DOTALL,
)


def _import_every_model() -> None:
    """Populate the registry; a model in an unimported module is not mapped."""
    for module in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module(f"app.models.{module.name}")


def _baseline_table_bodies() -> dict[str, str]:
    sql = BASELINE_SQL.read_text(encoding="utf-8")
    return {match.group(1): match.group(2) for match in _CREATE_TABLE.finditer(sql)}


def _column_ddl(body: str, column_name: str) -> str | None:
    for raw in body.splitlines():
        if re.match(rf"\s*{re.escape(column_name)}\s+\S", raw):
            return raw.strip().rstrip(",")
    return None


def _declares_default(column_ddl: str, column_name: str) -> bool:
    """True when the DDL carries a DEFAULT clause.

    The column name is dropped first: ``default_policy_id UUID`` contains the
    word DEFAULT without declaring one.
    """
    remainder = column_ddl[len(column_name) :]
    return re.search(r"\bDEFAULT\b", remainder, re.IGNORECASE) is not None


def test_model_server_default_matches_baseline_ddl() -> None:
    _import_every_model()
    bodies = _baseline_table_bodies()
    assert bodies, f"parsed no CREATE TABLE out of {BASELINE_SQL}"

    mismatches: list[str] = []

    for mapper in BaseModel.registry.mappers:
        table = mapper.class_.__table__
        body = bodies.get(table.name)
        if body is None:
            continue  # created by a later migration; out of scope here.

        for column in table.columns:
            if column.primary_key:
                continue
            column_ddl = _column_ddl(body, column.name)
            if column_ddl is None:
                continue  # added by a later migration.

            baseline_has = _declares_default(column_ddl, column.name)
            model_claims = column.server_default is not None
            if baseline_has == model_claims:
                continue
            # A Python-side default fills the value before the INSERT, so the
            # database default is never consulted and drift cannot bite.
            if not baseline_has and column.default is not None:
                continue

            if model_claims:
                # str() renders the SQL text; repr() would print an object address.
                claimed = str(column.server_default.arg).strip()
                problem = (
                    f"model declares server_default={claimed!r} but the "
                    "baseline has none, so SQLAlchemy omits the column and "
                    "PostgreSQL stores NULL"
                )
            else:
                problem = (
                    "baseline declares a DEFAULT but the model does not, so "
                    "SQLAlchemy sends an explicit NULL and the default never "
                    "applies"
                )
            mismatches.append(
                f"{table.name}.{column.name} (nullable={column.nullable}): {problem}\n"
                f"    baseline: {column_ddl}"
            )

    assert not mismatches, (
        "server_default drift between ORM models and the frozen baseline.\n"
        "The baseline is the schema authority (AGENTS.md 9), so align the "
        "model unless a new Alembic revision changes the database.\n\n" + "\n".join(mismatches)
    )
