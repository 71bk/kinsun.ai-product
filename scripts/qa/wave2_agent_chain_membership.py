"""Owner-approved, four-hour synthetic staff membership; never repairs legacy rows."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

RUN = "wave2-agent-chain-20260908"
MEMBERSHIP = str(uuid5(NAMESPACE_URL, f"kinsun:{RUN}:membership"))
STAFF = "20000000-0000-4000-8000-000000000010"
TENANT = "10000000-0000-4000-8000-000000000001"
UNIT = "30000000-0000-4000-8000-000000000001"
ROLE = "DAYCARE_CARE_WORKER"


def validate_command(command: str, allow_write: bool) -> None:
    if command not in {"inspect", "prepare", "expire"}:
        raise RuntimeError("Unknown command")
    if command != "inspect" and not allow_write:
        raise RuntimeError("Explicit --allow-synthetic-write is required")


def expiry_cutoff(row: dict, now: datetime) -> datetime:
    if not row or any(
        str(row.get(key)) != expected
        for key, expected in {
            "membership_id": MEMBERSHIP,
            "actor_id": STAFF,
            "tenant_id": TENANT,
            "care_unit_id": UNIT,
            "role_code": ROLE,
        }.items()
    ):
        raise RuntimeError("Membership ownership mismatch")
    end = row.get("effective_to")
    if not isinstance(end, datetime) or end.tzinfo is None:
        raise RuntimeError("Expected bounded membership")
    return min(end, now - timedelta(seconds=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="inspect",
        choices=["inspect", "prepare", "expire"],
    )
    parser.add_argument("--allow-synthetic-write", action="store_true")
    args = parser.parse_args()
    validate_command(args.command, args.allow_synthetic_write)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/core-api"))
    from sqlalchemy import create_engine, text
    from wave2_agent_chain_inspect import validate_target

    from app.core.config import get_settings
    from app.database_url import to_psycopg_database_url

    settings = get_settings()
    validate_target(settings.app_env, settings.database_url)
    engine = create_engine(
        to_psycopg_database_url(settings.database_url),
        hide_parameters=True,
        connect_args={"connect_timeout": 10},
    )
    params = {
        "id": MEMBERSHIP,
        "actor": STAFF,
        "tenant": TENANT,
        "unit": UNIT,
        "role": ROLE,
    }
    select_sql = """
        SELECT membership_id,actor_id,tenant_id,care_unit_id,role_code,status,
               effective_from,effective_to
        FROM eldercare_ai.actor_tenant_membership WHERE membership_id=CAST(:id AS uuid)
    """
    try:
        with engine.begin() as connection:
            if args.command == "inspect":
                connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '10000'"))
            row = (
                connection.execute(
                    text(select_sql + (" FOR UPDATE" if args.command == "expire" else "")),
                    params,
                )
                .mappings()
                .one_or_none()
            )
            if args.command == "prepare":
                if row is not None:
                    raise RuntimeError("Campaign already exists; never overwrite or renew it")
                owner_ok = connection.scalar(
                    text("""
                    SELECT EXISTS (
                      SELECT 1 FROM eldercare_ai.actor a
                      JOIN eldercare_ai.actor_tenant_membership m ON m.actor_id=a.actor_id
                      JOIN eldercare_ai.care_unit u ON u.care_unit_id=CAST(:unit AS uuid)
                        AND u.tenant_id=m.tenant_id
                      WHERE a.actor_id=CAST(:actor AS uuid)
                      AND CAST(a.actor_type AS text)=:role AND a.status='ACTIVE'
                      AND m.tenant_id=CAST(:tenant AS uuid)
                      AND m.care_unit_id IS NULL AND m.role_code=:role
                      AND m.status='ACTIVE' AND m.effective_from<=now()
                      AND (m.effective_to IS NULL OR m.effective_to>now())
                    )
                """),
                    params,
                )
                if not owner_ok:
                    raise RuntimeError("Synthetic staff or tenant/unit ownership unavailable")
                now = datetime.now(UTC)
                connection.execute(
                    text("""
                    INSERT INTO eldercare_ai.actor_tenant_membership
                    (membership_id,actor_id,tenant_id,care_unit_id,role_code,status,effective_from,effective_to)
                    VALUES (CAST(:id AS uuid),CAST(:actor AS uuid),CAST(:tenant AS uuid),
                            CAST(:unit AS uuid),:role,'ACTIVE',:start,:end)
                """),
                    {**params, "start": now, "end": now + timedelta(hours=4)},
                )
            elif args.command == "expire":
                cutoff = expiry_cutoff(dict(row) if row else {}, datetime.now(UTC))
                connection.execute(
                    text(
                        "UPDATE eldercare_ai.actor_tenant_membership SET effective_to=:end "
                        "WHERE membership_id=CAST(:id AS uuid)"
                    ),
                    {**params, "end": cutoff},
                )
            row = connection.execute(text(select_sql), params).mappings().one_or_none()
        print(
            json.dumps(
                {"command": args.command, "membership": dict(row) if row else None},
                default=str,
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
