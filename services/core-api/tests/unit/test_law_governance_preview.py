from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts/rag/preview_law_governance_sync.py"
spec = importlib.util.spec_from_file_location("law_governance_preview", SCRIPT)
assert spec is not None and spec.loader is not None
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


@pytest.fixture
def inputs():
    record = {
        "identity": {"chunk_id": "synthetic_1", "source_id": preview.SOURCE},
        "content": {
            "text": "Synthetic public knowledge",
            "embedding_text": "Synthetic public knowledge",
            "text_sha256": preview.sha(b"Synthetic public knowledge"),
            "embedding_text_sha256": preview.sha(b"Synthetic public knowledge"),
        },
        "governance": {
            "current_status": "current",
            "review_status": "needs_review",
            "production_approved": False,
        },
        "retrieval_policy": {
            "risk_level": "low",
            "stop_normal_rag": False,
            "requires_official_assessment": False,
            "requires_professional_assessment": None,
            "retrieval_eligible": False,
            "retrieval_block_reasons": [preview.MISSING],
            "allowed_audiences": ["elder"],
            "allowed_purposes": ["legal_reference"],
        },
    }
    stopped = copy.deepcopy(record)
    stopped["identity"]["chunk_id"] = "synthetic_stopped"
    stopped["retrieval_policy"].update(stop_normal_rag=True, risk_level="high_red_line")
    candidate = {
        "prior_chunk_id": "synthetic_1",
        "chunk_id": "synthetic_successor_1",
        "source_id": preview.SOURCE,
        "requires_professional_assessment": True,
        "source_allowed_purposes": ["legal_reference"],
        "chunk_allowed_purposes": ["legal_reference"],
        "retrieval_audiences": ["elder"],
        "text_sha256": record["content"]["text_sha256"],
        "embedding_text_sha256": record["content"]["embedding_text_sha256"],
    }
    policy = {
        "candidate_binding": {
            "source_release_id": preview.RELEASE,
            "embedding_profile_id": preview.PROFILE,
        },
        "chunks": [candidate],
    }
    authority = {
        "gates": {"external_sync": "NOT_AUTHORIZED", "production_approved": False},
        "assessment_null_decision": {
            "scope": "ORDINARY_RUNTIME_CANDIDATES_ONLY",
            "requires_professional_assessment_null_value": True,
        },
    }
    return [record, stopped], policy, authority


def run(inputs):
    return preview.build_preview(*inputs, expected_total=2, expected_scope=1, expected_pool=1)


def test_pure_deterministic_scoped_preview(inputs):
    before = copy.deepcopy(inputs)
    result = run(inputs)
    assert inputs == before
    assert result == run(inputs)
    assert result["changed_records"] == result["unchanged_records"] == 1
    assert result["excluded_law_ids"] == ["synthetic_stopped"]
    change = result["changes"][0]
    assert change["before_record_sha256"] != change["hypothetical_record_sha256"]
    before_policy = change["before_retrieval_policy"]
    after_policy = change["hypothetical_retrieval_policy"]
    assert {key for key in before_policy if before_policy[key] != after_policy[key]} == {
        "requires_professional_assessment",
        "retrieval_eligible",
        "retrieval_block_reasons",
    }
    assert result["live_database_checked"] is False
    assert result["external_sync"] == "NOT_AUTHORIZED"
    assert "Synthetic public knowledge" not in json.dumps(result)


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("governance", "current_status", "superseded"),
        ("governance", "review_status", "verified"),
        ("governance", "production_approved", True),
        ("governance", "production_approved", 0),
        ("retrieval_policy", "stop_normal_rag", True),
        ("retrieval_policy", "stop_normal_rag", 0),
        ("retrieval_policy", "risk_level", "high_red_line"),
        ("retrieval_policy", "requires_official_assessment", None),
        ("retrieval_policy", "requires_official_assessment", "false"),
        ("retrieval_policy", "requires_professional_assessment", True),
        ("retrieval_policy", "retrieval_eligible", True),
        ("retrieval_policy", "retrieval_block_reasons", [preview.MISSING, "revoked"]),
        ("content", "text", "changed"),
        ("content", "embedding_text", "changed"),
        ("identity", "source_id", "another_source"),
    ],
)
def test_rejects_record_drift(inputs, section, key, value):
    inputs[0][0][section][key] = value
    with pytest.raises(preview.PreviewError):
        run(inputs)


@pytest.mark.parametrize(
    "key,value",
    [
        ("requires_professional_assessment", "true"),
        ("text_sha256", "0" * 64),
        ("embedding_text_sha256", "0" * 64),
        ("source_allowed_purposes", []),
        ("chunk_allowed_purposes", []),
        ("retrieval_audiences", []),
    ],
)
def test_rejects_policy_drift(inputs, key, value):
    inputs[1]["chunks"][0][key] = value
    with pytest.raises(preview.PreviewError):
        run(inputs)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "release", "profile", "authority"])
def test_rejects_scope_drift(inputs, kind):
    if kind == "missing":
        inputs[0][0]["identity"]["chunk_id"] = "not_in_pool"
    elif kind == "duplicate":
        inputs[0][1]["identity"]["chunk_id"] = "synthetic_1"
    elif kind in ("release", "profile"):
        key = "source_release_id" if kind == "release" else "embedding_profile_id"
        inputs[1]["candidate_binding"][key] = "other"
    else:
        inputs[2]["assessment_null_decision"]["scope"] = "ALL"
    with pytest.raises(preview.PreviewError):
        run(inputs)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b"\xef\xbb\xbf{}", b"{}\r\n", b"[]"])
def test_strict_json(raw):
    with pytest.raises(preview.PreviewError):
        preview.parse(raw)


@pytest.mark.parametrize("path", ["../escape", "/escape", "C:/escape", "..\\escape"])
def test_rejects_unsafe_paths(tmp_path, path):
    with pytest.raises(preview.PreviewError):
        preview.within(tmp_path, path)


def test_inventory_detects_unlisted_and_changed_files(tmp_path):
    artifact = tmp_path / "data.json"
    artifact.write_bytes(b"{}\n")
    raw = f"{preview.sha(artifact.read_bytes())}  data.json\n".encode()
    (tmp_path / "SHA256SUMS.txt").write_bytes(raw)
    assert preview.inventory(tmp_path, preview.sha(raw)) == {"data.json": b"{}\n"}
    (tmp_path / "unlisted.json").write_bytes(b"{}\n")
    with pytest.raises(preview.PreviewError, match="INVENTORY_COVERAGE_MISMATCH"):
        preview.inventory(tmp_path, preview.sha(raw))
    artifact.write_bytes(b'{"changed":true}\n')
    with pytest.raises(preview.PreviewError, match="ARTIFACT_HASH_MISMATCH"):
        preview.inventory(tmp_path, preview.sha(raw))


def test_cli_sanitizes_unexpected_errors(monkeypatch, capsys):
    def fail(_):
        raise ValueError("secret should never be printed")

    monkeypatch.setattr(preview, "preview_repository", fail)
    assert preview.main([]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAIL",
        "code": "INVALID_OR_UNAVAILABLE_INPUT",
    }


def test_cli_has_no_apply_or_output_mode():
    for arg in ("--apply", "--output", "--policy-sha"):
        with pytest.raises(SystemExit) as error:
            preview.main([arg])
        assert error.value.code == 2


def test_missing_record_and_policy_duplicate(inputs):
    with pytest.raises(preview.PreviewError, match="RECORD_COUNT_MISMATCH"):
        preview.build_preview(
            inputs[0][:1], *inputs[1:], expected_total=2, expected_scope=1, expected_pool=1
        )
    inputs[1]["chunks"].append(copy.deepcopy(inputs[1]["chunks"][0]))
    with pytest.raises(preview.PreviewError, match="DUPLICATE_POLICY_ID"):
        preview.build_preview(*inputs, expected_total=2, expected_scope=1, expected_pool=2)


def test_changed_inventory_pin(tmp_path):
    (tmp_path / "SHA256SUMS.txt").write_bytes(b"unexpected\n")
    with pytest.raises(preview.PreviewError, match="INVENTORY_PIN_MISMATCH"):
        preview.inventory(tmp_path, "0" * 64)


def test_authority_cannot_expand_to_external_or_production(inputs):
    inputs[2]["gates"]["external_sync"] = "AUTHORIZED"
    with pytest.raises(preview.PreviewError, match="AUTHORITY_SCOPE_CHANGED"):
        run(inputs)
    inputs[2]["gates"]["external_sync"] = "NOT_AUTHORIZED"
    inputs[2]["gates"]["production_approved"] = True
    with pytest.raises(preview.PreviewError, match="PRODUCTION_NOT_ALLOWED"):
        run(inputs)


def test_import_has_no_environment_or_io_side_effects(monkeypatch):
    import builtins
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("Import must not read files or connect")

    module_spec = importlib.util.spec_from_file_location("preview_no_io", SCRIPT)
    assert module_spec is not None and module_spec.loader is not None
    source = SCRIPT.read_text(encoding="utf-8")
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(Path, "read_bytes", deny)
    monkeypatch.setattr(socket, "socket", deny)
    exec(compile(source, str(SCRIPT), "exec"), module.__dict__)


def test_repository_pinned_preview_is_offline(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("Network must not be used")

    monkeypatch.setattr(socket, "socket", denied)
    result = preview.preview_repository(ROOT)
    assert result["total_records"] == 726
    assert result["changed_records"] == 71
    assert result["unchanged_records"] == 655
    assert result["excluded_law_ids"] == [preview.SOURCE + "_rag_v2_v002_0048"]
    assert any(x["prior_chunk_id"].endswith("_0002") for x in result["changes"])
