"""Offline safety checks for the read-only live-chain evidence helper."""

import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[4] / "scripts/qa/wave2_agent_chain_inspect.py"
SPEC = importlib.util.spec_from_file_location("wave2_agent_chain_inspect", PATH)
assert SPEC and SPEC.loader
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def test_accepts_explicit_development_supabase_target():
    helper.validate_target("development", "postgresql+asyncpg://u:p@demo.supabase.com/postgres")


@pytest.mark.parametrize(
    "environment,url",
    [
        ("production", "postgresql+asyncpg://u:p@demo.supabase.com/postgres"),
        ("test", "postgresql+asyncpg://u:p@demo.supabase.com/postgres"),
        ("development", "postgresql+asyncpg://u:p@localhost/postgres"),
        ("development", "postgresql+asyncpg://u:p@demo.supabase.com/other"),
        ("development", "postgresql://u:p@demo.supabase.com/postgres"),
        ("development", "postgresql+asyncpg://u:p@demo.supabase.com.evil.invalid/postgres"),
    ],
)
def test_refuses_other_targets_without_leaking_url(environment, url):
    with pytest.raises(RuntimeError) as error:
        helper.validate_target(environment, url)
    assert url not in str(error.value)


@pytest.mark.parametrize("query", helper.QUERIES.values())
def test_queries_are_read_only_and_bounded(query):
    assert query.lstrip().startswith("SELECT ")
    assert ";" not in query
    assert ":run" in query or ":session_key" in query
    assert "SELECT *" not in query
    assert "response_body" not in query
    assert "structured_payload" not in query


def test_environment_and_database_imports_are_lazy():
    # The module can be imported by tests without reading developer configuration.
    assert "get_settings" not in vars(helper)
    assert "create_engine" not in vars(helper)
