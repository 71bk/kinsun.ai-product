"""Build the current OpenSearch transport-governance audit v008."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = REPOSITORY_ROOT / "services" / "rag-ingestion" / "src"
sys.path.insert(0, str(SERVICE_ROOT))

from rag_ingestion.source_family_policy_audit_v8 import (  # noqa: E402
    SourceFamilyPolicyAuditV8Error,
    build_source_family_policy_audit_v8,
)


def main() -> int:
    try:
        summary = build_source_family_policy_audit_v8(REPOSITORY_ROOT)
    except SourceFamilyPolicyAuditV8Error as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
