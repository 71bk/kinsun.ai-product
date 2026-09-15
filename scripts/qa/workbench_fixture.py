"""Isolated, opt-in workbench acceptance campaign; reuses audited retirement."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "workbench_previous_fixture", Path(__file__).with_name("previous_record_fixture.py")
)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

from sqlalchemy import select  # noqa: E402

from app.models.care_action import CareAction  # noqa: E402

base.CAMPAIGN = "workbench-real-auth-20260915"
base.MARKER = "Synthetic Workbench 20260915"
base.IDS = {key: uuid5(NAMESPACE_URL, f"kinsun:{base.CAMPAIGN}:{key}") for key in base.KEYS}
base.PRIVATE = ROOT / ".qa/.env.workbench-real-auth"
base.NOTE = (
    "Synthetic workbench handover 20260915: human-authored planned activity, no live care data."
)
base.SCOPES = [*base.SCOPES, "assignment:start", "care_action:read"]
TASK_KEYS = ("OPEN", "IN_PROGRESS", "POSTPONED")
original_prepare = base.prepare
original_inspect = base.inspect


async def prepare(session, settings):
    await original_prepare(session, settings)
    # Only freshly inserted rows in this still-uncommitted campaign are adjusted.
    current = await session.get(base.CareAssignment, base.IDS["current"])
    current.status, current.version = "CONFIRMED", 1
    no_scope = await session.get(base.CareAssignment, base.IDS["no_history"])
    no_scope.service_scope = [
        scope for scope in no_scope.service_scope if scope != "care_action:read"
    ]
    for state in TASK_KEYS:
        session.add(
            CareAction(
                id=uuid5(NAMESPACE_URL, f"kinsun:{base.CAMPAIGN}:task:{state}"),
                tenant_id=base.IDS["tenant"],
                elder_id=base.IDS["elder"],
                action_type="FOLLOW_UP",
                title=f"Synthetic workbench {state}",
                description=f"Synthetic follow-up {state}: confirm next activity arrangement.",
                trigger_reason="Synthetic human-authored acceptance fixture",
                related_event_ids=[],
                assignee_actor_id=base.IDS["reader"],
                created_by_actor_id=base.IDS["reader"],
                due_at=datetime.now(UTC) + timedelta(days=1),
                status=state,
                priority="LOW",
                version=1,
            )
        )
    await session.flush()


async def inspect(session):
    result = await original_inspect(session)
    tasks = (
        await session.scalars(
            select(CareAction)
            .where(CareAction.tenant_id == base.IDS["tenant"])
            .order_by(CareAction.id)
        )
    ).all()
    result["tasks"] = [
        {"id": str(row.id), "status": row.status, "version": row.version} for row in tasks
    ]
    result["task_sha256"] = hashlib.sha256(
        json.dumps(
            [
                {col.key: getattr(row, col.key) for col in type(row).__mapper__.column_attrs}
                for row in tasks
            ],
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    return result


base.prepare, base.inspect = prepare, inspect

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["inspect", "prepare", "expire-reader", "retire"],
        nargs="?",
        default="inspect",
    )
    parser.add_argument("--allow-synthetic-write", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(base.run(args.command, args.allow_synthetic_write))
    except Exception as error:
        print(json.dumps({"result": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
