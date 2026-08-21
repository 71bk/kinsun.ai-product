# RagChunkV2 Local Candidates

This directory holds immutable, local-only successor artifacts for the frozen
17-source, 726-chunk RAG corpus. It is not an ingestion input and does not grant
production approval.

The active audit-renewal path is deliberately three phase:

1. `preflight/v005/` freezes every implementation, test, and RAG contract
   input with a strict raw UTF-8 LF byte hash mode. It also locks every
   immutable candidate and every prior formal artifact.
2. `evidence/v005/` is generated after preflight. Its JUnit report embeds the
   validation-input inventory digest, and its atomic execution receipt records
   the portable display command, exact subprocess argv, exit code, timestamps,
   and JUnit SHA-256. `test-evidence.json` binds those files to the inventory.
3. The validator checks immutable `candidates/v002/` against both its original
   v003 package evidence and the current v005 audit evidence. It never rewrites
   the candidate merely because validation code or adjacent contracts changed.

The immutable `candidates/v001/` package remains bound to
`contracts/schemas/rag/rag-chunk-v2.schema.json` (`2.0.0`). The active
`candidates/v002/` successor is bound to the separate
`contracts/schemas/rag/rag-chunk-v2.1.schema.json` (`2.1.0`); the newer schema
does not redefine or broaden the historical v001 contract.

`preflight/v001/` through `preflight/v004/`, `evidence/v001/` through
`evidence/v004/`, and `candidates/v001/` are retained immutable historical
attempts. The v003 evidence remains the immutable package evidence copied into
v002. The v004 audit exposed that audit-bound reports must be excluded from the
deterministic core rebuild comparison; it remains preserved as a failed audit.
The v001 package is anchored in Git commit
`ea221208f9e9d3d84c982b147db6197bd3af2b14`. The v005 prior lock verifies the
internal checksums of both immutable candidates and locks their current bytes.

All successor chunks retain `review_status=needs_review`,
`human_source_review=not_completed`, `ingestion_status=staging`, and
`production_approved=false`. The 14 Taiwanese official sources are identified
separately from the three public research/scale sources; research evidence is
never promoted to official authority.

Run from the repository root:

```powershell
uv run --project services/rag-ingestion python scripts/rag/build_v2_artifacts.py preflight
uv run --project services/rag-ingestion python scripts/rag/build_v2_artifacts.py evidence
uv run --project services/rag-ingestion python scripts/rag/validate_v2_artifacts.py
```

These commands make no Bedrock, OpenSearch, cloud-storage, or other external
service calls. The `build` subcommand remains available for deterministic
rebuild checks in a fresh output root; it will not replace the canonical v002
candidate. A new version must be used instead of replacing any existing output.
