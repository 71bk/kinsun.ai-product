"""Build or validate the immutable law-sync v010 audit."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/rag-ingestion/src"))
from rag_ingestion.source_family_policy_audit_v10 import build, validate  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate"))
    args = parser.parse_args()
    print(
        json.dumps(
            (build if args.command == "build" else validate)(ROOT), sort_keys=True
        )
    )
