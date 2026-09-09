"""Real PostgreSQL regressions for SELECT autobegin and failed-body cleanup."""

from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.actor import Actor
from tests.committed_session import committed_session_scope

ACTOR_ID = UUID("61000000-0000-4000-a000-000000000001")


@pytest_asyncio.fixture(loop_scope="function")
async def committed_actor_with_open_read(committed_session):
    assert await committed_session.get(Actor, ACTOR_ID) is None
    committed_session.add(
        Actor(id=ACTOR_ID, actor_type="HOME_CARE_WORKER", display_name="Synthetic fixture worker")
    )
    await committed_session.commit()
    # Deliberately leave a live connection crossing the fixture/body boundary.
    assert await committed_session.scalar(select(Actor.id).where(Actor.id == ACTOR_ID)) == ACTOR_ID
    return ACTOR_ID


@pytest.mark.parametrize("iteration", [0, 1])
async def test_open_read_is_released_between_tests(
    committed_session, committed_actor_with_open_read, iteration
):
    assert iteration in (0, 1)
    assert await committed_session.get(Actor, committed_actor_with_open_read) is not None
    # No commit/rollback here: the fixture must close this transaction on its own loop.
    assert committed_session.in_transaction()


async def test_failed_body_is_cleaned_before_next_session(test_engine):
    with pytest.raises(AssertionError, match="synthetic body failure"):
        async with committed_session_scope(test_engine) as session:
            session.add(
                Actor(id=ACTOR_ID, actor_type="HOME_CARE_WORKER", display_name="Synthetic worker")
            )
            await session.commit()
            assert await session.get(Actor, ACTOR_ID) is not None
            raise AssertionError("synthetic body failure")
    # Uses the same lifecycle as the fixture, without relying on test ordering.
    async with committed_session_scope(test_engine) as session:
        assert await session.get(Actor, ACTOR_ID) is None
        session.add(
            Actor(id=ACTOR_ID, actor_type="HOME_CARE_WORKER", display_name="Synthetic next worker")
        )
        await session.commit()
