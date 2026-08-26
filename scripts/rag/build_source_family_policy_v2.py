from __future__ import annotations

import json
import sys
from pathlib import Path


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_builder():
    root = _repository_root()
    source_root = root / "services/rag-ingestion/src"
    if source_root.as_posix() not in sys.path:
        sys.path.insert(0, source_root.as_posix())
    from rag_ingestion.source_family_policy_v2 import (  # noqa: PLC0415
        build_owner_source_family_policy_acceptance,
        build_source_family_policy_v2,
        build_source_family_policy_v2_audit_preflight,
        build_source_family_policy_v2_preflight,
    )

    return (
        build_owner_source_family_policy_acceptance,
        build_source_family_policy_v2_preflight,
        build_source_family_policy_v2,
        build_source_family_policy_v2_audit_preflight,
    )


def main() -> int:
    root = _repository_root()
    build_acceptance, build_preflight, build_policy, build_audit = _load_builder()
    summaries = [
        build_acceptance(root).to_dict(),
        build_preflight(root).to_dict(),
        build_policy(root).to_dict(),
        build_audit(root).to_dict(),
    ]
    print(
        json.dumps(
            {
                "artifacts": summaries,
                "external_sync": "NOT_AUTHORIZED",
                "production_approved": False,
                "status": "PASS",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
