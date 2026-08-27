"""Validate owner acceptance v004 and immutable runtime policy v002."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = REPOSITORY_ROOT / "services" / "rag-ingestion" / "src"
sys.path.insert(0, str(SERVICE_ROOT))

from rag_ingestion.source_family_runtime_policy_v2 import (  # noqa: E402
    SourceFamilyRuntimePolicyV2Error,
    validate_owner_assessment_response_acceptance,
    validate_source_family_runtime_policy_v2,
)


def main() -> int:
    try:
        acceptance = validate_owner_assessment_response_acceptance(REPOSITORY_ROOT)
        policy = validate_source_family_runtime_policy_v2(REPOSITORY_ROOT)
    except SourceFamilyRuntimePolicyV2Error as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {"status": "PASS", "acceptance": acceptance, "runtime_policy": policy},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
