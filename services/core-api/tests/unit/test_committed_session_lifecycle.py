"""DB-free cleanup fault injection and fixture-loop regression checks."""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests import committed_session as lifecycle


@pytest.mark.parametrize("failed", [(), ("rollback",), ("close",), ("rollback", "close")])
async def test_cleanup_releases_before_truncate_and_reports_errors(monkeypatch, failed):
    session = MagicMock()
    operations = []
    errors = {name: RuntimeError(name) for name in failed}

    def operation(name):
        async def run():
            operations.append(name)
            if name in errors:
                raise errors[name]

        return AsyncMock(side_effect=run)

    for name in ("rollback", "close", "invalidate"):
        setattr(session, name, operation(name))

    async def truncate(engine):
        operations.append("truncate")

    monkeypatch.setattr(lifecycle, "truncate_test_tables", truncate)
    if failed:
        with pytest.raises(ExceptionGroup) as raised:
            await lifecycle.cleanup_committed_session(session, MagicMock())
        assert raised.value.exceptions == tuple(errors.values())
    else:
        await lifecycle.cleanup_committed_session(session, MagicMock())
    assert operations == ["rollback", "close", *(["invalidate"] if failed else []), "truncate"]


async def test_unreleased_connection_does_not_attempt_truncate(monkeypatch):
    session = MagicMock()
    session.rollback = AsyncMock(side_effect=RuntimeError("rollback"))
    session.close = AsyncMock(side_effect=RuntimeError("close"))
    session.invalidate = AsyncMock(side_effect=RuntimeError("invalidate"))
    truncate = AsyncMock()
    monkeypatch.setattr(lifecycle, "truncate_test_tables", truncate)
    with pytest.raises(ExceptionGroup) as raised:
        await lifecycle.cleanup_committed_session(session, MagicMock())
    assert len(raised.value.exceptions) == 3
    truncate.assert_not_awaited()


async def test_truncate_failure_is_not_suppressed(monkeypatch):
    session = MagicMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    failure = RuntimeError("truncate")
    monkeypatch.setattr(lifecycle, "truncate_test_tables", AsyncMock(side_effect=failure))
    with pytest.raises(ExceptionGroup) as raised:
        await lifecycle.cleanup_committed_session(session, MagicMock())
    assert raised.value.exceptions == (failure,)


@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_body_failure_remains_visible_during_cleanup(monkeypatch, cleanup_fails):
    body_error = AssertionError("synthetic body failure")
    cleanup_error = RuntimeError("synthetic cleanup failure")
    cleanup = AsyncMock(side_effect=cleanup_error if cleanup_fails else None)
    monkeypatch.setattr(lifecycle, "cleanup_committed_session", cleanup)
    monkeypatch.setattr(lifecycle, "async_sessionmaker", MagicMock())
    with pytest.raises(RuntimeError if cleanup_fails else AssertionError) as raised:
        async with lifecycle.committed_session_scope(MagicMock()):
            raise body_error
    cleanup.assert_awaited_once()
    if cleanup_fails:
        assert raised.value is cleanup_error
        assert raised.value.__context__ is body_error
    else:
        assert raised.value is body_error


def test_committed_session_and_dependent_async_fixtures_use_function_loop():
    directory = Path(__file__).parents[1] / "integration"
    fixtures = {}
    for path in directory.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if isinstance(target, ast.Attribute) and target.attr == "fixture":
                    fixtures[node.name] = (node, decorator)
    consumers = {"committed_session"}
    while True:
        added = {
            name
            for name, (node, _) in fixtures.items()
            if any(arg.arg in consumers for arg in node.args.args)
        } - consumers
        if not added:
            break
        consumers.update(added)
    assert {"seed_api_data", "care_data", "voice_data", "negative_authorization_data"} <= consumers
    for name in consumers:
        _, decorator = fixtures[name]
        assert isinstance(decorator, ast.Call), name
        assert any(
            kw.arg == "loop_scope"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value == "function"
            for kw in decorator.keywords
        ), name
