"""Generate a local projection-binding successor without changing v003 policy bytes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = "data/rag-v2/candidates/v004"
CANDIDATE_SHA = "f3339ceae77c380f42b3c2823b28216827ef48d057129a9c5f5edd40c9e808dd"
BASE = "data/rag-v3/governance/source-family-policy/runtime/candidates/v003/source-family-runtime-policy.json"
BASE_SHA = "99aa1dd6ccf90970c798664fedaff9ae3dd2f769437ebebc4a54c07478a1b5bd"
DESTINATION = "data/rag-v3/governance/source-family-policy/runtime/candidates/v004"


def encode(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()


def build_files(root: Path) -> dict[str, bytes]:
    # Function-local imports: importing this command never loads settings or connects.
    sys.path.insert(0, str(root / "services/agent-runtime/src"))
    from agent_runtime.rag.runtime_policy import RuntimePolicyDocumentV4

    candidate = root / CANDIDATE
    spec = importlib.util.spec_from_file_location(
        "law_policy_preview", root / "scripts/rag/preview_law_governance_sync.py"
    )
    if spec is None or spec.loader is None:
        raise ValueError("PREVIEW_UNAVAILABLE")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    # The Core loader already accepted this exact pinned candidate. Recheck every
    # byte here without merging the incompatible Core and Agent environments.
    helper.inventory(candidate, CANDIDATE_SHA)
    base_raw = (root / BASE).read_bytes()
    if hashlib.sha256(base_raw).hexdigest() != BASE_SHA:
        raise ValueError("POLICY_PIN_MISMATCH")
    crosswalk_raw = (candidate / "crosswalk/chunk-id-crosswalk-v004.jsonl").read_bytes()
    payload = {
        "schema_version": "4.0.0",
        "runtime_policy_version": "v004",
        "base_policy_sha256": BASE_SHA,
        "base_policy": json.loads(base_raw),
        "projection_binding": {
            "release_id": f"rag-v2-v004-{CANDIDATE_SHA[:12]}",
            "candidate_sha256": CANDIDATE_SHA,
            "embedding_profile_id": "ep-google-00a12ec45096fa9d97d9e9b6",
            "crosswalk_sha256": hashlib.sha256(crosswalk_raw).hexdigest(),
            "prior_release_id": "rag-v2-v002-bab68588963b",
            "id_mapping": "PRESERVE_SOURCE_AND_INDEX_V002_TO_V004",
            "production_approved": False,
        },
    }
    files = {
        "source-family-runtime-policy.json": encode(payload),
        "runtime-policy-v004.schema.json": encode(
            RuntimePolicyDocumentV4.model_json_schema()
        ),
        "prior-artifact-lock.json": encode(
            [
                {"path": BASE, "size_bytes": len(base_raw), "sha256": BASE_SHA},
                {
                    "path": CANDIDATE + "/SHA256SUMS.txt",
                    "sha256": CANDIDATE_SHA,
                    "size_bytes": (candidate / "SHA256SUMS.txt").stat().st_size,
                },
            ]
        ),
        "README.md": (
            "# Projection binding v004\n\n"
            "Local candidate only, not external sync or production approval.\n"
            "The full v003 response policy remains independently hash-pinned.\n"
            "Only projection lookup IDs move to v004; citation IDs remain v003.\n"
            "All live current/stop/eligibility/block/review gates remain mandatory.\n"
        ).encode(),
    }
    files["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(raw).hexdigest()}  {path}\n"
        for path, raw in sorted(files.items())
    ).encode()
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args(argv)
    try:
        files = build_files(ROOT)
        from agent_runtime.rag.runtime_policy import load_source_family_runtime_policy

        with tempfile.TemporaryDirectory(
            prefix="law-policy-pending-", dir=ROOT / ".qa"
        ) as scratch:
            directory = Path(scratch) / "v004"
            directory.mkdir()
            for relative, raw in files.items():
                (directory / relative).write_bytes(raw)
            digest = hashlib.sha256(
                files["source-family-runtime-policy.json"]
            ).hexdigest()
            policy = load_source_family_runtime_policy(
                directory / "source-family-runtime-policy.json", expected_sha256=digest
            )
            if files != build_files(ROOT):
                raise ValueError("INPUT_CHANGED")
            if args.build:
                destination = ROOT / DESTINATION
                if destination.exists():
                    raise ValueError("DESTINATION_EXISTS")
                directory.rename(destination)
            print(
                json.dumps(
                    {
                        "status": "LOCAL_CANDIDATE_CREATED"
                        if args.build
                        else "VALIDATED_DRY_RUN",
                        "policy_sha256": digest,
                        "candidate_count": len(policy.candidate_chunk_ids),
                        "external_sync": "NOT_AUTHORIZED",
                        "production_approved": False,
                    }
                )
            )
        return 0
    except Exception:
        print(
            json.dumps({"status": "FAIL", "code": "POLICY_CANDIDATE_VALIDATION_FAILED"})
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
