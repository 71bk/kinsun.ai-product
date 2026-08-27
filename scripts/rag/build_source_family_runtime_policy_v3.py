"""Build owner authorization v005 and immutable runtime policy v003."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = REPOSITORY_ROOT / "services" / "rag-ingestion" / "src"
sys.path.insert(0, str(SERVICE_ROOT))

from rag_ingestion.source_family_runtime_policy_v3 import (
    SourceFamilyRuntimePolicyV3Error,
    build_owner_purpose_classification_acceptance,
    build_source_family_runtime_policy_v3,
)


def main() -> int:
    try:
        build_owner_purpose_classification_acceptance(REPOSITORY_ROOT)
        summary = build_source_family_runtime_policy_v3(REPOSITORY_ROOT)
    except SourceFamilyRuntimePolicyV3Error as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
