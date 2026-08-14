"""Unit tests for the bounded confirmed-memory context query."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.repositories.memory_repo import MemoryRepository


@pytest.mark.asyncio
async def test_active_context_query_is_tenant_scoped_and_bounded() -> None:
    session = AsyncMock()
    result = MagicMock()
    memory_id = uuid4()
    result.all.return_value = [(memory_id, 3, "PREFERENCE", "喜歡在下午聽老歌。", 4)]
    session.execute.return_value = result

    records = await MemoryRepository(session, uuid4()).list_active_context_for_elder(
        elder_id=uuid4(),
        max_consent_version=4,
        limit=5,
    )

    assert records[0].memory_id == memory_id
    assert records[0].version == 3
    assert records[0].content == "喜歡在下午聽老歌。"
    assert records[0].consent_version == 4

    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
    assert "memory.tenant_id" in compiled
    assert "memory.elder_id" in compiled
    assert "memory.status" in compiled
    assert "memory.deleted_at IS NULL" in compiled
    assert "memory.consent_version" in compiled
    assert "memory_version.version_status" in compiled
    assert "memory_version.valid_to IS NULL" in compiled
    assert "char_length(" in compiled
    assert "memory_version.content" in compiled
    assert "graph_projection_record" in compiled
    assert "graph_projection_record.projection_status" in compiled
    assert "graph_projection_record.source_version = eldercare_ai.memory.current_version" in compiled
    assert statement._limit_clause.value == 5
