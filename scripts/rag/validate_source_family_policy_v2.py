from __future__ import annotations

import json
import sys
from pathlib import Path


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_validators():
    root = _repository_root()
    source_root = root / "services/rag-ingestion/src"
    if source_root.as_posix() not in sys.path:
        sys.path.insert(0, source_root.as_posix())
    from rag_ingestion.source_family_policy_v2 import (  # noqa: PLC0415
        validate_owner_source_family_policy_acceptance,
        validate_source_family_policy_v2,
        validate_source_family_policy_v2_audit_preflight,
        validate_source_family_policy_v2_build_preflight_snapshot,
    )

    return (
        validate_owner_source_family_policy_acceptance,
        validate_source_family_policy_v2_build_preflight_snapshot,
        validate_source_family_policy_v2,
        validate_source_family_policy_v2_audit_preflight,
    )


def main() -> int:
    root = _repository_root()
    validate_acceptance, validate_preflight, validate_policy, validate_audit = _load_validators()
    print(
        json.dumps(
            {
                "acceptance": validate_acceptance(root),
                "audit_preflight": validate_audit(root),
                "external_sync": "NOT_AUTHORIZED",
                "policy": validate_policy(root),
                "preflight": validate_preflight(root),
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
