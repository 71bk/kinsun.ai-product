# RagChunkV2 Local Candidates

This directory holds immutable, local-only successor artifacts for the frozen
17-source, 726-chunk RAG corpus. It is not an ingestion input and does not grant
production approval.

The active audit path is deliberately three phase:

1. `preflight/v003/` freezes every implementation and test input with a
   strict raw UTF-8 LF byte hash mode, and locks every prior formal artifact
   before conversion.
2. `evidence/v003/` is generated after preflight. Its JUnit report embeds the
   validation-input inventory digest, and its atomic execution receipt records
   the portable display command, exact subprocess argv, exit code, timestamps,
   and JUnit SHA-256.
3. `candidates/v002/` is created atomically only when the frozen inventories,
   prior lock, and bound passing test evidence still match.

The immutable `candidates/v001/` package remains bound to
`contracts/schemas/rag/rag-chunk-v2.schema.json` (`2.0.0`). The active
`candidates/v002/` successor is bound to the separate
`contracts/schemas/rag/rag-chunk-v2.1.schema.json` (`2.1.0`); the newer schema
does not redefine or broaden the historical v001 contract.

`preflight/v001/`, `preflight/v002/`, `evidence/v001/`, `evidence/v002/`, and
`candidates/v001/` are retained immutable historical attempts. They are
superseded and must not be treated as the active review candidate.
The v001 package is anchored in Git commit
`ea221208f9e9d3d84c982b147db6197bd3af2b14`; v003 additionally verifies its
internal `SHA256SUMS.txt` and locks the bytes observed at preflight.

All successor chunks retain `review_status=needs_review`,
`human_source_review=not_completed`, `ingestion_status=staging`, and
`production_approved=false`. The 14 Taiwanese official sources are identified
separately from the three public research/scale sources; research evidence is
never promoted to official authority.

Run from the repository root:

```powershell
uv run --project services/rag-ingestion python scripts/rag/build_v2_artifacts.py preflight
uv run --project services/rag-ingestion python scripts/rag/build_v2_artifacts.py evidence
uv run --project services/rag-ingestion python scripts/rag/build_v2_artifacts.py build
uv run --project services/rag-ingestion python scripts/rag/validate_v2_artifacts.py
```

These commands make no Bedrock, OpenSearch, cloud-storage, or other external
service calls. A new artifact version must be used instead of replacing an
existing preflight or candidate directory.
