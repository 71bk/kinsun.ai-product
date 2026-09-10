"""Offline, stdout-only law governance delta; never an importable release or approval.

No environment loading, database clients, provider calls, file writes or apply mode.
Run from any directory with Python 3.12; inputs are independently hash-pinned.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
BASE = "data/rag-v2/candidates/v002"
POLICY = (
    "data/rag-v3/governance/source-family-policy/runtime/candidates/v003/"
    "source-family-runtime-policy.json"
)
AUTHORITY = "data/rag-v3/review/acceptance/v004/owner-assessment-response-policy-acceptance.json"
BASE_SHA = "bab68588963be5b47c7058f9cb9b5c0fd87181087316c262c9faefea6d5bedec"
POLICY_SHA = "99aa1dd6ccf90970c798664fedaff9ae3dd2f769437ebebc4a54c07478a1b5bd"
AUTHORITY_SHA = "dcc923a3910e556c535a26856644fabc097a78b36e2a2492409ee987ce106c69"
SOURCE = "moj_long_term_care_services_act_20210609"
RELEASE = "rag-v2-v002-bab68588963b"
PROFILE = "ep-google-00a12ec45096fa9d97d9e9b6"
MISSING = "requires_professional_assessment_missing"


class PreviewError(ValueError):
    """Only fixed internal codes may reach stdout; never rejected input values."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PreviewError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest(value: object) -> str:
    return sha(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def decode(raw: bytes) -> str:
    require(
        not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw, "NON_CANONICAL_TEXT"
    )
    return raw.decode("utf-8")


def parse(raw: bytes) -> dict:
    value = json.loads(decode(raw), object_pairs_hook=unique_object)
    require(isinstance(value, dict), "EXPECTED_OBJECT")
    return value


def within(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    require(
        bool(relative)
        and "\\" not in relative
        and ":" not in relative
        and not path.is_absolute()
        and ".." not in path.parts,
        "UNSAFE_PATH",
    )
    resolved = (root / relative).resolve()
    require(resolved.is_relative_to(root.resolve()), "UNSAFE_PATH")
    return resolved


def inventory(root: Path, expected_sha: str) -> dict[str, bytes]:
    raw = (root / "SHA256SUMS.txt").read_bytes()
    require(sha(raw) == expected_sha, "INVENTORY_PIN_MISMATCH")
    files: dict[str, bytes] = {}
    resolved_paths: set[Path] = set()
    for line in decode(raw).splitlines():
        require(bool(line) and "  " in line, "INVALID_INVENTORY")
        expected, relative = line.split("  ", 1)
        target = within(root, relative)
        require(target not in resolved_paths, "DUPLICATE_INVENTORY_PATH")
        resolved_paths.add(target)
        content = target.read_bytes()
        require(sha(content) == expected, "ARTIFACT_HASH_MISMATCH")
        decode(content)
        files[relative] = content
    actual = {
        p.resolve()
        for p in root.rglob("*")
        if p.is_file() and p.name != "SHA256SUMS.txt"
    }
    require(actual == resolved_paths, "INVENTORY_COVERAGE_MISMATCH")
    return files


def build_preview(
    records: list[dict],
    policy: dict,
    authority: dict,
    *,
    expected_total: int = 726,
    expected_scope: int = 71,
    expected_pool: int = 554,
) -> dict:
    """Pure hypothetical delta. Test counts may vary; CLI pins are not configurable."""
    require(
        authority["gates"]["external_sync"] == "NOT_AUTHORIZED",
        "AUTHORITY_SCOPE_CHANGED",
    )
    require(
        authority["gates"]["production_approved"] is False, "PRODUCTION_NOT_ALLOWED"
    )
    decision = authority["assessment_null_decision"]
    require(
        decision["scope"] == "ORDINARY_RUNTIME_CANDIDATES_ONLY",
        "INVALID_AUTHORITY_SCOPE",
    )
    require(
        decision["requires_professional_assessment_null_value"] is True,
        "INVALID_DECISION",
    )
    require(
        policy["candidate_binding"]["source_release_id"] == RELEASE, "RELEASE_MISMATCH"
    )
    require(
        policy["candidate_binding"]["embedding_profile_id"] == PROFILE,
        "PROFILE_MISMATCH",
    )
    pool = policy["chunks"]
    require(len(pool) == expected_pool, "POOL_COUNT_MISMATCH")
    require(
        len({c["prior_chunk_id"] for c in pool}) == len(pool), "DUPLICATE_POLICY_ID"
    )
    scope = {c["prior_chunk_id"]: c for c in pool if c["source_id"] == SOURCE}
    require(len(scope) == expected_scope, "SCOPE_COUNT_MISMATCH")
    require(len(records) == expected_total, "RECORD_COUNT_MISMATCH")
    ids = [record["identity"]["chunk_id"] for record in records]
    require(len(set(ids)) == len(ids), "DUPLICATE_RECORD_ID")
    require(set(scope).issubset(ids), "MISSING_SCOPED_RECORD")
    before_hashes: dict[str, str] = {}
    after_hashes: dict[str, str] = {}
    changes = []
    excluded_law_ids = []
    for record in sorted(records, key=lambda item: item["identity"]["chunk_id"]):
        chunk_id = record["identity"]["chunk_id"]
        content = record["content"]
        for field in ("text", "embedding_text"):
            require(
                sha(content[field].encode()) == content[field + "_sha256"],
                "TEXT_HASH_MISMATCH",
            )
        before_hashes[chunk_id] = digest(record)
        after_hashes[chunk_id] = before_hashes[chunk_id]
        if chunk_id not in scope:
            if record["identity"]["source_id"] == SOURCE:
                excluded_law_ids.append(chunk_id)
            continue
        candidate = scope[chunk_id]
        retrieval = record["retrieval_policy"]
        governance = record["governance"]
        require(record["identity"]["source_id"] == SOURCE, "SOURCE_MISMATCH")
        require(
            candidate["requires_professional_assessment"] is True,
            "POLICY_ASSESSMENT_MISMATCH",
        )
        require(
            all(
                content[f] == candidate[f]
                for f in ("text_sha256", "embedding_text_sha256")
            ),
            "POLICY_TEXT_MISMATCH",
        )
        require(governance["current_status"] == "current", "NOT_CURRENT")
        require(governance["production_approved"] is False, "PRODUCTION_NOT_ALLOWED")
        require(governance["review_status"] == "needs_review", "REVIEW_STATE_CHANGED")
        require(retrieval["stop_normal_rag"] is False, "STOPPED")
        require(retrieval["risk_level"] in ("low", "medium"), "RISK_BLOCKED")
        require(
            type(retrieval["requires_official_assessment"]) is bool,
            "OFFICIAL_ASSESSMENT_MISSING",
        )
        require(
            retrieval["requires_professional_assessment"] is None,
            "ASSESSMENT_STATE_CHANGED",
        )
        require(retrieval["retrieval_eligible"] is False, "ELIGIBILITY_STATE_CHANGED")
        require(
            retrieval["retrieval_block_reasons"] == [MISSING], "UNRESOLVED_BLOCKERS"
        )
        require(
            "legal_reference" in candidate["source_allowed_purposes"]
            and "legal_reference" in candidate["chunk_allowed_purposes"]
            and "elder" in candidate["retrieval_audiences"],
            "POLICY_SCOPE_DENIED",
        )
        proposed = copy.deepcopy(record)
        proposed["retrieval_policy"].update(
            requires_professional_assessment=True,
            retrieval_eligible=True,
            retrieval_block_reasons=[],
        )
        after_hashes[chunk_id] = digest(proposed)
        changes.append(
            {
                "prior_chunk_id": chunk_id,
                "policy_chunk_id": candidate["chunk_id"],
                "before_record_sha256": before_hashes[chunk_id],
                "hypothetical_record_sha256": after_hashes[chunk_id],
                "before_retrieval_policy": retrieval,
                "hypothetical_retrieval_policy": proposed["retrieval_policy"],
            }
        )
    return {
        "schema_version": "1.0.0",
        "mode": "OFFLINE_DELTA_NOT_A_RELEASE_OR_APPLY_MANIFEST",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
        "live_database_checked": False,
        "embedding_vectors_checked": False,
        "base_release_id": RELEASE,
        "total_records": len(records),
        "changed_records": len(changes),
        "unchanged_records": len(records) - len(changes),
        "before_records_digest": digest(before_hashes),
        "hypothetical_records_digest": digest(after_hashes),
        "excluded_law_ids": excluded_law_ids,
        "changes": changes,
        "remaining_gates": [
            "SUCCESSOR_SCHEMA_AND_IDS",
            "LIVE_DRIFT_CHECK",
            "EXTERNAL_APPROVAL",
            "VECTOR_INTEGRITY",
            "STAGING_RETRIEVAL_AND_SAFETY_TESTS",
        ],
    }


def preview_repository(root: Path) -> dict:
    files = inventory(root / BASE, BASE_SHA)
    policy_raw = within(root, POLICY).read_bytes()
    authority_raw = within(root, AUTHORITY).read_bytes()
    require(sha(policy_raw) == POLICY_SHA, "POLICY_PIN_MISMATCH")
    require(sha(authority_raw) == AUTHORITY_SHA, "AUTHORITY_PIN_MISMATCH")
    policy, authority = parse(policy_raw), parse(authority_raw)
    binding = policy["assessment_acceptance_binding"]
    require(
        binding["path"] == AUTHORITY and binding["sha256"] == AUTHORITY_SHA,
        "BINDING_MISMATCH",
    )
    records = []
    for relative, raw in sorted(files.items()):
        if relative.startswith("chunks/") and relative.endswith(".jsonl"):
            for line in decode(raw).splitlines():
                require(bool(line.strip()), "BLANK_JSONL_LINE")
                records.append(parse(line.encode()))
    result = build_preview(records, policy, authority)
    result["input_inventory"] = [
        {"path": BASE + "/" + path, "size_bytes": len(raw), "sha256": sha(raw)}
        for path, raw in sorted(files.items())
    ] + [
        {"path": path, "size_bytes": len(raw), "sha256": sha(raw)}
        for path, raw in (
            (BASE + "/SHA256SUMS.txt", (root / BASE / "SHA256SUMS.txt").read_bytes()),
            (POLICY, policy_raw),
            (AUTHORITY, authority_raw),
        )
    ]
    # A concurrent edit must not leave a report that attests to mixed input states.
    for item in result["input_inventory"]:
        require(
            sha(within(root, item["path"]).read_bytes()) == item["sha256"],
            "INPUT_CHANGED",
        )
    require(
        sha((root / BASE / "SHA256SUMS.txt").read_bytes()) == BASE_SHA, "INPUT_CHANGED"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)  # Deliberately no --apply, --output or pin override.
    try:
        result = preview_repository(ROOT)
    except Exception as exc:
        code = (
            str(exc)
            if isinstance(exc, PreviewError)
            else "INVALID_OR_UNAVAILABLE_INPUT"
        )
        print(json.dumps({"status": "FAIL", "code": code}))
        return 1
    print(json.dumps({"status": "PASS", **result}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
