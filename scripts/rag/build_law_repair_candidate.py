"""Build a local, immutable v004 projection candidate; no external activation.

Default: validate in memory and print a bounded receipt. --build publishes the
fixed new local directory only after the existing projection loader accepts it.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = "data/rag-v2/candidates/v004"
VERSION = "v004"
REPAIR_SCHEMA = "schemas/rag-law-repair-chunk-v004.schema.json"


def preview_module(root: Path):
    spec = importlib.util.spec_from_file_location(
        "law_repair_preview", root / "scripts/rag/preview_law_governance_sync.py"
    )
    if spec is None or spec.loader is None:
        raise ValueError("PREVIEW_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def encode(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def build_files(root: Path) -> tuple[dict[str, bytes], dict]:
    helper = preview_module(root)
    preview = helper.preview_repository(root)
    schema_path = "contracts/schemas/rag/rag-chunk-v2.1.schema.json"
    schema_raw = (root / schema_path).read_bytes()
    helper.require(
        helper.sha(schema_raw)
        == "639d4d3d562980f386dbcd1735fd0d42c5ce9d2633d8784652cf50ff43ce4acb",
        "BASE_SCHEMA_PIN_MISMATCH",
    )
    preview["input_inventory"].append(
        {
            "path": schema_path,
            "size_bytes": len(schema_raw),
            "sha256": helper.sha(schema_raw),
        }
    )
    originals = helper.inventory(root / helper.BASE, helper.BASE_SHA)
    changes = {row["prior_chunk_id"]: row for row in preview["changes"]}
    groups: dict[str, list] = defaultdict(list)
    crosswalk = []
    for path, raw in sorted(originals.items()):
        if not path.startswith("chunks/") or not path.endswith(".jsonl"):
            continue
        for line in raw.splitlines():
            old = helper.parse(line)
            new = copy.deepcopy(old)
            identity = new["identity"]
            prior_id = identity["chunk_id"]
            source_id = identity["source_id"]
            identity["prior_chunk_id"] = prior_id
            identity["prior_chunk_file_id"] = identity["chunk_file_id"]
            identity["chunk_file_id"] = f"{source_id}_rag_v2_{VERSION}"
            identity["chunk_id"] = (
                f"{identity['chunk_file_id']}_{identity['chunk_index']:04d}"
            )
            new["artifact_version"] = VERSION
            new["schema_version"] = "2.2.0"
            if prior_id in changes:
                helper.require(
                    helper.digest(old) == changes[prior_id]["before_record_sha256"],
                    "PREVIEW_RECORD_CHANGED",
                )
                new["retrieval_policy"] = copy.deepcopy(
                    changes[prior_id]["hypothetical_retrieval_policy"]
                )
            groups[source_id].append(new)
            crosswalk.append(
                {
                    "source_id": source_id,
                    "prior_chunk_id": prior_id,
                    "chunk_id": identity["chunk_id"],
                    "prior_record_sha256": helper.digest(old),
                    "record_sha256": helper.digest(new),
                    "text_sha256": new["content"]["text_sha256"],
                    "embedding_text_sha256": new["content"]["embedding_text_sha256"],
                    "governance_changed": prior_id in changes,
                }
            )
    helper.require(len(crosswalk) == 726 and len(groups) == 17, "INCOMPLETE_SUCCESSOR")
    helper.require(
        len({row["chunk_id"] for row in crosswalk}) == 726, "DUPLICATE_SUCCESSOR_ID"
    )
    files: dict[str, bytes] = {}
    schema = helper.parse(schema_raw)
    schema["$id"] = (
        "https://kinsun.ai/contracts/schemas/rag/rag-law-repair-chunk-v004.schema.json"
    )
    schema["title"] = "RagLawRepairChunkV004"
    schema["description"] = (
        "Local staging v004 governance repair; no external activation or production approval."
    )
    schema["properties"]["artifact_version"] = {"const": VERSION}
    schema["properties"]["schema_version"] = {"const": "2.2.0"}
    files[REPAIR_SCHEMA] = encode(schema)
    manifest_files = []
    entries = []
    for source_id, records in sorted(groups.items()):
        records.sort(key=lambda record: record["identity"]["chunk_index"])
        path = f"chunks/{source_id}.rag-chunk-v2.{VERSION}.jsonl"
        files[path] = b"".join(encode(record) for record in records)
        manifest_files.append(
            {
                "source_id": source_id,
                "path": path,
                "chunk_count": len(records),
                "sha256": helper.sha(files[path]),
            }
        )
        entries.extend(
            {
                "chunk_id": record["identity"]["chunk_id"],
                "text_sha256": record["content"]["text_sha256"],
                "embedding_text_sha256": record["content"]["embedding_text_sha256"],
            }
            for record in records
        )
    files[f"manifests/source-manifest-{VERSION}.json"] = encode(
        {
            "artifact_version": VERSION,
            "source_count": 17,
            "chunk_count": 726,
            "sources": [{"source_id": source} for source in sorted(groups)],
        }
    )
    files[f"manifests/chunk-file-manifest-{VERSION}.json"] = encode(
        {
            "artifact_version": VERSION,
            "chunk_file_count": 17,
            "chunk_count": 726,
            "files": manifest_files,
        }
    )
    files[f"manifests/embedding-staging-allowlist-{VERSION}.json"] = encode(
        {
            "artifact_version": VERSION,
            "source_count": 17,
            "chunk_count": 726,
            "human_source_review": "NOT_COMPLETED",
            "embedding_status": "NOT_STARTED",
            "production_status": "BLOCKED",
            "external_sync": "NOT_AUTHORIZED",
            "entries": entries,
        }
    )
    files[f"crosswalk/chunk-id-crosswalk-{VERSION}.jsonl"] = b"".join(
        encode(row) for row in sorted(crosswalk, key=lambda row: row["prior_chunk_id"])
    )
    files["prior-artifact-lock.json"] = encode(preview["input_inventory"])
    files["repair-lineage.json"] = encode(
        {
            "schema_version": "1.0.0",
            "artifact_version": VERSION,
            "prior_release_id": helper.RELEASE,
            "prior_candidate_sha256": helper.BASE_SHA,
            "runtime_policy_sha256": helper.POLICY_SHA,
            "assessment_acceptance_sha256": helper.AUTHORITY_SHA,
            "embedding_profile_id": helper.PROFILE,
            "governance_changes": 71,
            "content_changes": 0,
            "remaining_governance_unchanged": 655,
            "external_sync": "NOT_AUTHORIZED",
            "production_approved": False,
            "embedding_reuse": "REQUIRES_LIVE_VECTOR_INTEGRITY_CHECK",
            "runtime_compatibility": "REQUIRES_SUCCESSOR_BINDING",
        }
    )
    files["README.md"] = (
        "# Law governance repair projection v004\n\n"
        "Local staging candidate only; no external sync or production approval.\n"
        "726 new IDs, 71 assessment-policy corrections; all text unchanged.\n"
        "Remaining 655 records retain their governance, including stop/high-risk restrictions.\n"
        "Generated manifests are projection-import indexes, not new source-review evidence.\n"
        "Crosswalk preserves lineage; old releases remain unchanged.\n"
        "Existing runtime policy v003 cannot select these new IDs.\n"
        "Do not activate without compatible runtime binding, live drift/vector checks and approval.\n"
    ).encode()
    files["SHA256SUMS.txt"] = "".join(
        f"{helper.sha(raw)}  {path}\n" for path, raw in sorted(files.items())
    ).encode()
    for item in preview["input_inventory"]:
        helper.require(
            helper.sha((root / item["path"]).read_bytes()) == item["sha256"],
            "INPUT_CHANGED",
        )
    return files, preview


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build", action="store_true", help="Publish a new local v004 directory only"
    )
    args = parser.parse_args(argv)
    try:
        files, preview = build_files(ROOT)
        sys.path.insert(0, str(ROOT / "services/core-api"))
        from app.rag_projection_importer import load_projection_batch

        # Scratch is outside artifact discovery; TemporaryDirectory owns its cleanup.
        with tempfile.TemporaryDirectory(
            prefix="law-repair-pending-", dir=ROOT / ".qa"
        ) as scratch:
            candidate = Path(scratch) / VERSION
            for relative, raw in files.items():
                target = candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            batch = load_projection_batch(
                candidate,
                candidate / REPAIR_SCHEMA,
                expected_source_count=17,
                expected_chunk_count=726,
            )
            helper = preview_module(ROOT)
            for item in preview["input_inventory"]:
                helper.require(
                    helper.sha((ROOT / item["path"]).read_bytes()) == item["sha256"],
                    "INPUT_CHANGED",
                )
            if args.build:
                destination = ROOT / DESTINATION
                if destination.exists():
                    raise ValueError("DESTINATION_EXISTS")
                # Same-volume publication; on Windows rename refuses an existing target.
                candidate.rename(destination)
            print(
                json.dumps(
                    {
                        "status": "LOCAL_CANDIDATE_CREATED"
                        if args.build
                        else "VALIDATED_DRY_RUN",
                        "release_id": batch.release_id,
                        "candidate_sha256": batch.candidate_sha256,
                        "chunk_count": batch.chunk_count,
                        "governance_changes": 71,
                        "external_sync": "NOT_AUTHORIZED",
                    }
                )
            )
        return 0
    except Exception:
        print(json.dumps({"status": "FAIL", "code": "CANDIDATE_VALIDATION_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
