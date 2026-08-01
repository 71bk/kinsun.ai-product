"""Negative authorization tests through the real HTTP and repository stack.

These tests use PostgreSQL-backed repositories instead of replacing an invalid
authorization source with ``None`` in a mock. They prove that cross-tenant and
cross-elder access, expired assignments, and revoked family relationships are
all hidden behind the same response as a nonexistent Elder.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.models.care_assignment import CareAssignment
from app.models.care_relationship import CareRelationship
from app.models.outbox import OutboxEvent
from tests.integration import test_identity_api as identity_api_tests

# Reuse the established synthetic Identity/Elder API seed. Re-exporting the
# decorated fixtures makes them available to this module's fixture namespace.
api_ids = identity_api_tests.api_ids
seed_api_data = identity_api_tests.seed_api_data

NONEXISTENT_ELDER_ID = uuid.UUID("99999999-9999-4999-9999-999999999999")


@pytest_asyncio.fixture
async def negative_authorization_data(committed_session, seed_api_data):
    """Add invalid authorization sources that must never grant access."""
    ids = seed_api_data
    now = datetime.now(UTC)

    committed_session.add_all(
        [
            CareRelationship(
                elder_id=ids["elder_2_id"],
                actor_id=ids["family_member_id"],
                tenant_id=ids["tenant_id"],
                care_unit_id=None,
                relationship_type="FAMILY_SHARE",
                scope=["elder:basic:read", "elder:access_context:read"],
                status="REVOKED",
                effective_from=now - timedelta(days=30),
                effective_to=None,
            ),
            CareAssignment(
                care_unit_id=ids["care_unit_id"],
                elder_id=ids["elder_1_id"],
                worker_id=ids["worker_id"],
                tenant_id=ids["tenant_id"],
                service_start=now - timedelta(days=2),
                service_end=now - timedelta(days=1),
                service_scope=["elder:basic:read", "elder:access_context:read"],
                status="CONFIRMED",
            ),
        ]
    )
    await committed_session.commit()

    yield ids


@pytest.fixture
def negative_authorization_count_context(
    negative_authorization_data,
    db_session,
):
    """Keep the count session inside, and shorter-lived than, seed cleanup."""
    return negative_authorization_data, db_session


def _build_app(test_engine, ids, actor_key: str, actor_role: str):
    return identity_api_tests._build_client_app(
        test_engine,
        actor_id=ids[actor_key],
        actor_role=actor_role,
        tenant_id=ids["tenant_id"],
    )


def _stable_error_body(response) -> dict:
    """Return public error fields while excluding the per-request correlation ID."""
    body = response.json()
    assert set(body) == {"error"}
    error = dict(body["error"])
    correlation_id = error.pop("correlation_id")
    uuid.UUID(correlation_id)
    return error


@pytest.mark.parametrize(
    ("scenario", "actor_key", "actor_role", "target_elder_key"),
    [
        (
            "cross_tenant",
            "family_member_id",
            "FAMILY_MEMBER",
            "elder_3_id",
        ),
        (
            "cross_elder",
            "daycare_worker_id",
            "DAYCARE_CARE_WORKER",
            "elder_2_id",
        ),
        (
            "expired_assignment",
            "worker_id",
            "HOME_CARE_WORKER",
            "elder_1_id",
        ),
        (
            "revoked_family_share",
            "family_member_id",
            "FAMILY_MEMBER",
            "elder_2_id",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
@pytest.mark.parametrize("suffix", ["", "/access-context"], ids=["elder", "access-context"])
@pytest.mark.asyncio
async def test_invalid_authorization_is_indistinguishable_from_nonexistent_elder(
    test_engine,
    negative_authorization_data,
    scenario: str,
    actor_key: str,
    actor_role: str,
    target_elder_key: str,
    suffix: str,
) -> None:
    """Every invalid scope returns the same safe 404 as a missing Elder."""
    ids = negative_authorization_data
    target_elder_id = ids[target_elder_key]
    app = _build_app(test_engine, ids, actor_key, actor_role)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        denied = await client.get(f"/api/v1/elders/{target_elder_id}{suffix}")
        nonexistent = await client.get(f"/api/v1/elders/{NONEXISTENT_ELDER_ID}{suffix}")

    assert denied.status_code == 404, scenario
    assert nonexistent.status_code == 404
    assert _stable_error_body(denied) == _stable_error_body(nonexistent)
    assert str(target_elder_id) not in denied.text
    assert "display_name" not in denied.text


@pytest.mark.asyncio
async def test_authorized_elder_lists_exclude_revoked_expired_and_cross_tenant_sources(
    test_engine,
    negative_authorization_data,
) -> None:
    """List endpoints expose only authorization sources valid at request time."""
    ids = negative_authorization_data

    family_app = _build_app(
        test_engine,
        ids,
        "family_member_id",
        "FAMILY_MEMBER",
    )
    async with AsyncClient(
        transport=ASGITransport(app=family_app),
        base_url="http://test",
    ) as client:
        family_response = await client.get("/api/v1/me/authorized-elders?mode=family")

    worker_app = _build_app(
        test_engine,
        ids,
        "worker_id",
        "HOME_CARE_WORKER",
    )
    async with AsyncClient(
        transport=ASGITransport(app=worker_app),
        base_url="http://test",
    ) as client:
        worker_response = await client.get("/api/v1/me/authorized-elders?mode=home-care")

    assert family_response.status_code == 200
    family_elder_ids = {item["elder_id"] for item in family_response.json()["data"]["items"]}
    assert family_elder_ids == {str(ids["elder_1_id"])}

    assert worker_response.status_code == 200
    worker_elder_ids = {item["elder_id"] for item in worker_response.json()["data"]["items"]}
    assert worker_elder_ids == {str(ids["elder_2_id"])}
    assert str(ids["elder_3_id"]) not in family_elder_ids | worker_elder_ids


async def _authorization_state_counts(session) -> tuple[int, int, int]:
    """Capture authorization-source and outbox row counts."""
    counts = []
    for model in (CareRelationship, CareAssignment, OutboxEvent):
        result = await session.execute(select(func.count()).select_from(model))
        counts.append(result.scalar_one())
    return tuple(counts)


@pytest.mark.asyncio
async def test_denied_reads_do_not_modify_authorization_state_or_outbox(
    test_engine,
    negative_authorization_count_context,
) -> None:
    """Authorization failures do not write domain state or outbox events."""
    ids, db_session = negative_authorization_count_context
    before = await _authorization_state_counts(db_session)
    app = _build_app(
        test_engine,
        ids,
        "family_member_id",
        "FAMILY_MEMBER",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        revoked = await client.get(f"/api/v1/elders/{ids['elder_2_id']}")
        cross_tenant = await client.get(f"/api/v1/elders/{ids['elder_3_id']}")

    after = await _authorization_state_counts(db_session)

    assert revoked.status_code == 404
    assert cross_tenant.status_code == 404
    assert after == before
