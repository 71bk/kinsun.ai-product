"""Disposable database checks for navigation and exact-assignment follow-up access."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.care_action import CareAction
from app.models.care_assignment import CareAssignment
from app.models.membership import ActorTenantMembership
from tests.integration.test_identity_api import (
    _build_client_app,
    _prepare_record_completion,
    api_ids,  # noqa: F401 -- fixture dependency
)
from tests.integration.test_identity_api import seed_api_data as _seed_api_data

workbench_data = _seed_api_data


@pytest.mark.asyncio
async def test_overlapping_visits_keep_dashboard_available_and_exact_scope_isolation(
    test_engine, workbench_data, committed_session
):
    ids = workbench_data
    current = await _prepare_record_completion(committed_session, ids)
    current.service_scope = ["assignment:read", "care_action:read"]
    restricted = CareAssignment(
        tenant_id=current.tenant_id,
        elder_id=current.elder_id,
        care_unit_id=current.care_unit_id,
        worker_id=current.worker_id,
        service_start=current.service_start,
        service_end=current.service_end,
        status="IN_PROGRESS",
        service_scope=["assignment:read"],
        version=1,
    )
    committed_session.add(restricted)
    await committed_session.commit()
    app = _build_client_app(test_engine, ids["worker_id"], "HOME_CARE_WORKER", ids["tenant_id"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dashboard = await client.get("/api/v1/me/authorized-elders?mode=home-care")
        assert dashboard.status_code == 200
        row = next(
            item
            for item in dashboard.json()["data"]["items"]
            if item["elder_id"] == str(current.elder_id)
        )
        assert row["open_care_action_count"] is None
        path = f"/api/v1/elders/{current.elder_id}/care-actions"
        assert (await client.get(path)).status_code == 404
        assert (
            await client.get(path, params={"assignment_id": str(current.id)})
        ).status_code == 200
        assert (
            await client.get(path, params={"assignment_id": str(restricted.id)})
        ).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "denial",
    [None, "scope", "task_scope", "worker", "tenant", "expired", "completed", "membership"],
)
async def test_selected_assignment_cannot_borrow_another_visits_grants(
    test_engine, workbench_data, committed_session, denial
):
    ids = workbench_data
    current = await _prepare_record_completion(committed_session, ids)
    current.service_scope = ["assignment:read", "care_action:read"]
    other = CareAssignment(
        tenant_id=current.tenant_id,
        elder_id=current.elder_id,
        care_unit_id=current.care_unit_id,
        worker_id=current.worker_id,
        service_start=current.service_start,
        service_end=current.service_end,
        status="IN_PROGRESS",
        service_scope=list(current.service_scope),
        version=1,
    )
    task = CareAction(
        tenant_id=current.tenant_id,
        elder_id=current.elder_id,
        action_type="FOLLOW_UP",
        title="Synthetic workbench task",
        description="Synthetic follow-up details",
        trigger_reason="Synthetic professional follow-up",
        related_event_ids=[],
        assignee_actor_id=current.worker_id,
        created_by_actor_id=current.worker_id,
        due_at=datetime.now(UTC) + timedelta(days=1),
        status="OPEN",
        priority="LOW",
        version=1,
    )
    committed_session.add_all([other, task])
    await committed_session.commit()
    actor_id, tenant_id = ids["worker_id"], ids["tenant_id"]
    if denial == "scope":
        current.service_scope = ["care_action:read"]
    elif denial == "task_scope":
        current.service_scope = ["assignment:read"]
    elif denial == "worker":
        actor_id = ids["daycare_worker_id"]
    elif denial == "tenant":
        tenant_id = ids["tenant_b_id"]
    elif denial == "expired":
        current.service_end = datetime.now(UTC) - timedelta(seconds=1)
    elif denial == "completed":
        current.status = "COMPLETED"
    elif denial == "membership":
        memberships = await committed_session.scalars(
            select(ActorTenantMembership).where(
                ActorTenantMembership.actor_id == actor_id,
            )
        )
        for membership in memberships:
            membership.effective_to = datetime.now(UTC) - timedelta(seconds=1)
            membership.effective_from = membership.effective_to - timedelta(days=1)
    await committed_session.commit()
    app = _build_client_app(test_engine, actor_id, "HOME_CARE_WORKER", tenant_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        detail = await client.get(f"/api/v1/home-care/assignments/{current.id}")
        tasks = await client.get(
            f"/api/v1/elders/{current.elder_id}/care-actions",
            params={"assignment_id": str(current.id), "status": "OPEN"},
        )
        wrong_elder = await client.get(
            f"/api/v1/elders/{ids['elder_1_id']}/care-actions",
            params={"assignment_id": str(current.id)},
        )
    assert detail.status_code == (200 if denial in {None, "task_scope"} else 404)
    assert tasks.status_code == (200 if denial is None else 404)
    assert wrong_elder.status_code == 404
    if denial is None:
        assert [row["care_action_id"] for row in tasks.json()["data"]["items"]] == [str(task.id)]
    else:
        assert "Synthetic follow-up" not in tasks.text
