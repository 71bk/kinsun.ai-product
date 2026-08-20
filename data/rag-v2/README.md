# RagChunkV2 Local Candidates

This directory holds immutable, local-only successor artifacts for the frozen
17-source, 726-chunk RAG corpus. It is not an ingestion input and does not grant
production approval.

The workflow is deliberately two phase:

1. `preflight/v002/` freezes the exact validation inputs and hashes every prior
   formal artifact before conversion. The retained `v001` lock records the
   pre-portability-fix attempt and is not overwritten.
2. `candidates/v001/` is created atomically only when the frozen inventories
   still match. Neither phase overwrites an existing version.

All successor chunks retain `review_status=needs_review`,
`human_source_review=not_completed`, `ingestion_status=staging`, and
`production_approved=false`. The 14 Taiwanese official sources are identified
separately from the three public research/scale sources; research evidence is
never promoted to official authority.

Run from the repository root:

```powershell
uv run --project services/rag-ingestion python scripts/rag/build_v2_artifacts.py preflight
uv run --project services/rag-ingestion pytest services/rag-ingestion/tests `
  --junitxml=data/rag-v2/evidence/v002/pytest-rag-ingestion.xml
uv run --project services/rag-ingestion python scripts/rag/build_v2_artifacts.py build
uv run --project services/rag-ingestion python scripts/rag/validate_v2_artifacts.py
```

These commands make no Bedrock, OpenSearch, cloud-storage, or other external
service calls. A new artifact version must be used instead of replacing an
existing preflight or candidate directory.
