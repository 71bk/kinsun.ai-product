from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("law_sync", ROOT / "scripts/rag/sync_law_repair.py")
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class FakeConnection:
    def __init__(self):
        self.events = []

    @contextmanager
    def transaction(self):
        self.events.append("BEGIN")
        try:
            yield
        except Exception:
            self.events.append("ROLLBACK")
            raise
        else:
            self.events.append("COMMIT")

    def execute(self, query):
        self.events.append(query)
        return SimpleNamespace(fetchone=lambda: ("on",))

    @contextmanager
    def cursor(self, **kwargs):
        yield self


@pytest.fixture
def prepared(monkeypatch):
    source, target, crosswalk, auth = sync.load_inputs()
    connection = FakeConnection()
    monkeypatch.setattr(sync, "load_inputs", lambda: (source, target, crosswalk, auth))

    def read(conn, batch, *, lock):
        conn.events.append("LOCK_SOURCE" if lock else "READ_SOURCE")
        return object(), [], []

    monkeypatch.setattr(sync, "read_snapshot", read)
    monkeypatch.setattr(
        sync,
        "export_batch",
        lambda directory, batch, *args, **kwargs: (
            SimpleNamespace(artifact_sha256="synthetic"),
            directory / batch.artifact_version,
        ),
    )
    monkeypatch.setattr(
        sync, "validate_embedding_reuse_snapshot", lambda **kwargs: {"status": "SYNTHETIC"}
    )
    monkeypatch.setattr(
        sync,
        "projection_rows",
        lambda *args, **kwargs: [
            {"release_id": target.release_id, **asdict(row)}
            for row in sorted(target.chunks, key=lambda x: x.chunk_id)
        ],
    )
    for name in ("import_projection", "import_embeddings"):

        def call(conn, batch, name=name):
            conn.events.append(name)
            return SimpleNamespace(to_dict=lambda: {"status": "SYNTHETIC"})

        monkeypatch.setattr(sync, name, call)
    monkeypatch.setattr(sync, "verify_embeddings", lambda *args: {"status": "SYNTHETIC"})
    return connection


def test_preflight_explicit_read_only_never_imports(prepared, tmp_path):
    result = sync.run(
        prepared, apply=False, expected_digest=None, directory=tmp_path, target_identity="test"
    )
    assert result["status"] == "PREFLIGHT_VALIDATED"
    assert "SET TRANSACTION READ ONLY" in prepared.events
    assert "SHOW transaction_read_only" in prepared.events
    assert "import_projection" not in prepared.events
    assert "import_embeddings" not in prepared.events


def test_apply_requires_matching_preflight_before_writes(prepared, tmp_path):
    with pytest.raises(sync.SyncValidationError, match="PREFLIGHT_DRIFT"):
        sync.run(
            prepared,
            apply=True,
            expected_digest="wrong",
            directory=tmp_path,
            target_identity="test",
        )
    assert "LOCK_SOURCE" in prepared.events
    assert prepared.events[-1] == "ROLLBACK"
    assert "import_projection" not in prepared.events


def test_apply_lock_then_both_imports_then_commit(prepared, tmp_path):
    preflight = sync.run(
        prepared, apply=False, expected_digest=None, directory=tmp_path, target_identity="test"
    )
    prepared.events.clear()
    result = sync.run(
        prepared,
        apply=True,
        expected_digest=preflight["preflight_sha256"],
        directory=tmp_path,
        target_identity="test",
    )
    assert result["status"] == "COMMITTED"
    events = prepared.events
    assert (
        events.index("LOCK_SOURCE")
        < events.index("import_projection")
        < events.index("import_embeddings")
    )
    assert events[-1] == "COMMIT"


@pytest.mark.parametrize("failure", ["import_embeddings", "verify_embeddings"])
def test_failure_after_projection_rolls_back_whole_transaction(
    prepared, tmp_path, monkeypatch, failure
):
    preflight = sync.run(
        prepared, apply=False, expected_digest=None, directory=tmp_path, target_identity="test"
    )
    prepared.events.clear()

    def fail(*args):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(sync, failure, fail)
    with pytest.raises(RuntimeError):
        sync.run(
            prepared,
            apply=True,
            expected_digest=preflight["preflight_sha256"],
            directory=tmp_path,
            target_identity="test",
        )
    assert "import_projection" in prepared.events
    assert prepared.events[-1] == "ROLLBACK"
    assert "COMMIT" not in prepared.events


def test_other_database_identity_invalidates_preflight(prepared, tmp_path):
    preflight = sync.run(
        prepared, apply=False, expected_digest=None, directory=tmp_path, target_identity="test"
    )
    with pytest.raises(sync.SyncValidationError, match="PREFLIGHT_DRIFT"):
        sync.run(
            prepared,
            apply=True,
            expected_digest=preflight["preflight_sha256"],
            directory=tmp_path,
            target_identity="other",
        )


def test_independent_verify_is_read_only_and_does_not_import(prepared, tmp_path):
    result = sync.run(
        prepared,
        apply=False,
        expected_digest=None,
        directory=tmp_path,
        target_identity="test",
        verify_target=True,
    )
    assert result["status"] == "VERIFIED"
    assert result["receipts"]["verification"]["status"] == "SYNTHETIC"
    assert "SET TRANSACTION READ ONLY" in prepared.events
    assert "import_projection" not in prepared.events


def test_target_metadata_drift_rolls_back(prepared, tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "projection_rows", lambda *args, **kwargs: [])
    with pytest.raises(sync.SyncValidationError, match="TARGET_READBACK_MISMATCH"):
        sync.run(
            prepared,
            apply=False,
            expected_digest=None,
            directory=tmp_path,
            target_identity="test",
            verify_target=True,
        )
    assert prepared.events[-1] == "ROLLBACK"


@pytest.mark.parametrize(
    "args",
    [
        ["apply"],
        ["apply", "--confirm-staging-write"],
        ["apply", "--expected-preflight-sha256", "a" * 64],
    ],
)
def test_apply_cli_requires_both_acknowledgements(args):
    with pytest.raises(SystemExit) as error:
        sync.main(args)
    assert error.value.code == 2
