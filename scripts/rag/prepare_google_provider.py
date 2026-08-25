"""Validate the Google document embedding profile without any external call."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "rag-ingestion" / "src"))

from rag_ingestion.cli import main  # noqa: E402


if __name__ == "__main__":
    os.environ.setdefault(
        "RAG_EMBEDDING_CONFIG_PATH",
        "config/rag/embedding-google.yaml",
    )
    raise SystemExit(main(["prepare-provider", "--repository-root", str(REPO_ROOT)]))
