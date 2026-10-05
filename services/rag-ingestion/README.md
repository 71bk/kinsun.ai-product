# RAG Ingestion Service

The current development retrieval path uses Supabase/PostgreSQL public RAG
projections and Google document/query embeddings, with release/profile/policy
configured in Agent Runtime. New local data preparation uses the command below.

## Local knowledge preparation (2026-10-02, phase 2)

From the repository root, inspect the supplied 735-chunk corpus without writes:

```powershell
uv run --project services/rag-ingestion python scripts/rag/prepare_knowledge.py
```

To write the local dataset and embedding work plan:

```powershell
uv run --project services/rag-ingestion python scripts/rag/prepare_knowledge.py --write --output .rag-work/knowledge-v007
```

The command retains 658 official chunks and excludes 75 non-official research/scale
references, one superseded flow and one navigation-only label. It preserves original
inputs and checks content hashes, IDs, metadata types, official URLs and source
locators. Short/long semantic units and unknown source currency produce warnings.
They are not new manual forms or claims of online freshness verification.

Output contains only `chunks.jsonl`, `report.json` and `embedding-plan.json`.
Identical repeated runs are supported; different output bytes require a different
explicit destination. This is a local preparation command, with no DB or provider
calls. `app.rag_knowledge_importer.load_knowledge_batch` independently validates
this dataset into a Core projection batch without importing or activating it.

The 631 unchanged embedding inputs and 27 changed inputs are a comparison with
v004, not proof that cached vectors are available. `--cache` accepts a local
`knowledge-embedding-cache-v1` object containing `profiles` (full seven-field
profile snapshots) and `entries` (embedding text, hash, profile ID and optional
vector). Only exact content and full profile matches with a valid supplied vector
count as `REUSE`. A metadata-only entry still needs embedding. No cache is supplied
by default, so the plan reports 0 available reuse and 658 required embeddings;
it does not execute them. The trusted registry is
`config/rag/knowledge-embedding-profiles.json`. Changing normalization, titles,
truncation or other preprocessing requires a new `config_version`/profile identity.

See [phase 2 usage and findings](../../docs/project/rag-simplification-phase2-20261002.md).

## Missing embeddings and a targeted audience correction

The optional audience patch changes only the independent public BA13 chunk to
also address family caregivers. It checks the original source, text hash and
audiences first; source text, review status and all other policy fields remain.

```powershell
uv run --project services/rag-ingestion python scripts/rag/prepare_knowledge.py --dataset-version v008 --audience-patches config/rag/knowledge-audience-patches.json --cache .rag-work/cache/v004-cache.json --write --output .rag-work/knowledge-v008
uv run --project services/rag-ingestion python scripts/rag/embed_knowledge.py --dataset .rag-work/knowledge-v008 --cache .rag-work/cache/v004-cache.json
```

The second command is a dry-run: it loads no credentials and calls no provider.
With this verified cache it reports 631 reusable vectors and 27 missing inputs.
Explicit `--generate --output .rag-work/cache/v008-complete-cache.json` generates
only missing unique inputs, using the same registered Google profile. At most
32 new inputs are permitted per invocation; existing output files are rejected.
The result is one complete cache, checked for profile, content hashes, vector
dimension, finite/nonzero values and full coverage. No database write occurs.
Run `prepare_knowledge.py` again with that cache to verify all 658 available.

On 2026-10-02 the 27 vectors were generated and the complete 658-vector cache
passed validation. Following explicit user authorization, candidate
`knowledge-v008-aae34e5095e6` was imported as 658 projections and 658 vectors in
one transaction. Readback verified content/profile/vector bindings and completed
receipts; v004 remained unchanged. Runtime configuration and activation are unchanged.

To independently validate the prepared projection and complete embedding cache:

```powershell
uv run --project services/core-api python scripts/rag/import_knowledge.py --expected-release-id knowledge-v008-aae34e5095e6 --expected-candidate-sha256 aae34e5095e6d02f57203939276f9abaf9b39db37b0eed3a54c19c68c87a7fb2
```

This command only produces a dry-run summary. It neither connects to the database
nor imports or activates a release; no write flag is provided.

## Development workflow

Code is versioned by Git. Keep real source provenance, source/data versions and
text/embedding-text content hashes; do not fabricate human `verified` status.
Current-byte audit successors, repeated code snapshots and per-change archival
packages are retired: do not create audit v021. The standalone answer-evidence
review UI/workbook entry points are retired; users need not fill 1,055 qrels.
Historical pinned packages remain unchanged as records of their capture time.

The new preparation/loader path has no manual review workbook, signed allowlist
or owner acceptance dependency. Review provenance and existing retrieval policy
remain truthful and unchanged. Existing runtime/SQL admission and production
authorization remain in force; preparing 658 chunks does not make all 658 eligible.
Phase 3 adjusts runtime and SQL together for natural-question Hybrid RAG, removing
exact-question matching, manual support sets, fixed answers and the three-citation
minimum. Phase 4 evaluates real questions; subsequent import/environment switching
and rollback require authorization. Phases 3 and 4 have now been implemented and
tested locally/live respectively; outstanding quality findings and import scope
are recorded in [the live test record](../../docs/project/rag-simplification-phase4-20261002.md).
Legacy human review/owner acceptance validators remain only where existing staging embedding,
verified-candidate or source-family tools depend on them; they are not mandatory
assignments for new development. See [phase 1 record](../../docs/project/rag-simplification-phase1-20261002.md).

## Legacy OpenSearch staging CLI

The remaining sections describe legacy Cohere/Bedrock/OpenSearch staging tooling.
Those tools validate the complete allowlisted dataset, embed it, ingest into a
fresh staging index and verify vectors before moving the staging alias. Their
compatibility gates below do not apply to the new local preparation command and
do not authorize provider switches or release activation.

## Legacy staging safety boundaries

- Only direct `*.jsonl` children of the configured approved directory are read.
- A path containing `pending-revalidation` is always rejected.
- Unknown, missing, or duplicate `chunk_id` values fail the complete run.
- `text` and `embedding_text` are hashed byte-for-byte as UTF-8 and compared
  with the Allowlist; neither field is modified.
- `RAG_ALLOWLIST_EXPECTED_SHA256` is always required and compared in constant
  time with the complete loaded Allowlist before Bedrock or OpenSearch starts.
- In staging only, `RAG_REQUIRE_OWNER_SIGNATURE=false` permits the supplied
  `NOT_SIGNED` owner-signature-pending Allowlist under the narrow
  `UNSIGNED_DEVELOPMENT_OVERRIDE`. It does not permit revoked/rejected state,
  malformed counts, hash mismatches, or chunks outside the Allowlist.
- Production context never uses the unsigned override. It requires an
  effective, formally signed, production-approved Allowlist and an enabled
  production switch; this first release still refuses every non-staging target.
- The current supplied Allowlist records Human Review as `NOT_COMPLETED`; the
  service carries that state into receipts and never upgrades it.
- The repository also contains the owner-reviewed, immutable local successor at
  `data/rag-v3/candidates/v003/`, where all 726 chunks are `verified`. It is not
  the currently supplied ingestion Allowlist and has not been synchronized to a
  Supabase release or activated by this service.
- Source-family policy v002 is a separate immutable staging overlay. It records
  owner-reviewed project use for 13 sources without a license URL, so the
  missing URL is not an automatic source block; legacy `license_status` values
  remain unchanged. Five owner-labelled general-risk form examples map to
  canonical `low` in policy only. Runtime integration and Golden Queries remain
  incomplete, so the overlay is not yet used by the current retrieval service.
- Missing, empty, or unsupported normal-RAG policy metadata never inherits a
  permissive default. Documents remain available in the staging index for
  review, but only documents with explicit current status, low/medium risk,
  nonempty audience and purpose scopes, and Boolean official/professional
  assessment flags receive `retrieval_eligible=true`.
- Embedding artifacts default to the OS temp directory at
  `kinsun-rag/embeddings.jsonl`. Any artifact path inside the repository is
  rejected. Receipts contain counts and governance state, never vectors or
  source text.
- A `VERIFIED_PENDING_ALIAS` receipt is durably written before alias cutover.
  If alias activation or the final `COMPLETED` receipt fails, the new index is
  removed and the prior single-target alias is restored when one existed.
- Index and alias names must explicitly contain `staging`; production-like
  names and non-staging mode are rejected.
- The staging collection uses OpenSearch Serverless NextGen `VECTORSEARCH`.
  Its ANN mapping is fail-closed to `knn_vector` / 1024 dimensions /
  `cosinesimil` / HNSW. NextGen selects the engine, so any `method.engine`
  configuration is rejected before an OpenSearch request.
- Search pipelines are reconciled before index creation. All existing pipeline
  definitions must match before any missing pipeline is written, and all
  acknowledged writes share one 0-to-60-second visibility window. A pipeline
  that remains invisible is retained for exact-match reconciliation on the
  next run; it is not deleted into an eventual-consistency tombstone.
- Serverless rejects the `wait_for` refresh policy, so bulk create does not
  request it. Post-ingest verification instead polls the document count over
  the same 0-to-60-second window; a count above the expected total is not a
  visibility delay and fails immediately. Requests use a 120-second timeout
  because a full staging bulk has been measured at roughly 24 seconds.

## Configuration

The CLI reads these checked-in files from `config/rag/` (or `--config-dir`):

- `embedding.yaml`
- `opensearch-index-v1.json`
- `hybrid-natural-language.json`
- `hybrid-legal.json`
- `staging-filters.yaml`
- `smoke-test.yaml`

Environment variables override config values. Required variables depend on
the operation: `AWS_REGION`, `BEDROCK_EMBEDDING_MODEL_ID`,
`BEDROCK_EMBEDDING_DIMENSION`, `OPENSEARCH_HOST`, `OPENSEARCH_INDEX`,
`OPENSEARCH_ALIAS`, `RAG_ALLOWLIST_PATH`, `RAG_CHUNKS_DIR`, and `RAG_MODE`.
Before any AWS operation, `RAG_ALLOWLIST_EXPECTED_SHA256` must also contain an
independently supplied SHA-256 that exactly matches the loaded Allowlist; the
manifest cannot attest itself. `RAG_REQUIRE_OWNER_SIGNATURE` defaults to
`false` for staging development, while `RAG_PRODUCTION_ENABLED` defaults to
`false` and cannot turn this staging-only release into a production writer.
`RAG_EMBEDDINGS_PATH` and `RAG_RECEIPT_PATH` are optional. AWS credentials use
the normal boto3 credential chain and must never be committed.

The individual config paths can be overridden with
`RAG_EMBEDDING_CONFIG_PATH`, `RAG_OPENSEARCH_INDEX_CONFIG_PATH`,
`RAG_HYBRID_NATURAL_CONFIG_PATH`, `RAG_HYBRID_LEGAL_CONFIG_PATH`, and
`RAG_STAGING_FILTERS_CONFIG_PATH`. `RAG_SMOKE_CONFIG_PATH` selects the two
end-to-end smoke requests, and `AGENT_RUNTIME_BASE_URL` supplies the reachable
runtime origin.

## Commands

### Historical metadata and review packages

`data/rag-v2/` and earlier acceptance/review outputs document their original
source versions and validation state. Their pinned bytes are preserved; code
changes no longer require frozen inventories, deterministic archival rebuilds
or a new review successor. `needs_review` remains an honest historical status.

The old human-review package and owner acceptance validators are retained for
compatibility with existing staging-embedding, verified-candidate and
source-family tools until phase 2. They are not the daily development path and
no new full-corpus manual assignment is required. The separate answer-evidence
review UI and workbook prepare/validate entry points are retired in this batch.

### Staging ingestion

From the repository root, run the required staging sequence:

```powershell
python scripts/rag/validate_allowlist.py
python scripts/rag/create_index.py
python scripts/rag/generate_embeddings.py
python scripts/rag/ingest.py
python scripts/rag/verify_index.py
python scripts/rag/smoke_test.py
```

The thin scripts delegate to these service subcommands:

```powershell
uv run --project services/rag-ingestion python -m rag_ingestion.cli validate-allowlist
uv run --project services/rag-ingestion python -m rag_ingestion.cli create-index
uv run --project services/rag-ingestion python -m rag_ingestion.cli generate-embeddings
uv run --project services/rag-ingestion python -m rag_ingestion.cli ingest
uv run --project services/rag-ingestion python -m rag_ingestion.cli verify-index
uv run --project services/rag-ingestion python -m rag_ingestion.cli smoke-test
```

For diagnostics outside that required six-step sequence, this read-only command
loads the same staging configuration and governance gate, then reads each
configured pipeline exactly once. It never creates, updates, deletes, or reads
an index, and reports only each pipeline name, visibility, and configuration
match state:

```powershell
python scripts/rag/inspect_pipelines.py
# or
uv run --project services/rag-ingestion python -m rag_ingestion.cli inspect-pipelines
```

Adding or editing an approved chunk means recomputing every hash the Allowlist
declares, which is the step most likely to go wrong by hand. This reports what
the approved JSONL files imply, and writes the manifest only with `--write`:

```powershell
python scripts/rag/rebuild_allowlist.py
python scripts/rag/rebuild_allowlist.py --write
```

It recomputes `text_sha256` and `embedding_text_sha256`, refreshes per-source
and total counts, and reports added, removed, and rehashed chunks. It never
touches governance: manifest status, owner risk acceptance, human review, and
production status are copied verbatim, and a chunk the manifest has not seen
before inherits `review_status=needs_review`, `human_source_review=NOT_COMPLETED`
and `production_gate=BLOCKED` rather than the state of its neighbours. A chunk
whose `source_id` has no reviewed `sources[]` entry is refused, because
`source_number` ties a source to the human review catalogue and a script must
not invent one.

Reformatting alone is reported as `UNCHANGED`; rewriting then would change the
Allowlist SHA-256 without any chunk differing, invalidating the attested
`RAG_ALLOWLIST_EXPECTED_SHA256` for nothing. When chunks really did change,
place the new SHA-256 into that variable by hand from an independently trusted
record, then rebuild the index: ingestion writes the complete approved set and
verifies an exact count, so it is a full rebuild rather than an append.

Every command prints a JSON summary without chunk text or vectors. Structural
validation can report `VALID` while `execution_allowed` is false; every command
that could contact AWS independently enforces the governance gate. Successful
summaries and every failure after governance evaluation include `governance_status` and
`production_approved`. Receipts persist those fields under `governance`; the
unsigned staging override records `UNSIGNED_DEVELOPMENT_OVERRIDE` and `false`.
The Bedrock, index, and bulk adapters are internal implementation boundaries;
operators must use the six repository scripts so the Allowlist and SHA gates run first.

`smoke-test` first verifies the alias, configured search pipelines, citation
identity, and mandatory `current_status=current` /
`stop_normal_rag=false` / `retrieval_eligible=true` / low-or-medium-risk
filters. It then POSTs the configured positive and
no-data cases to the Agent Runtime retrieval endpoint. A pass requires a
standard success envelope, three to five fully cited chunks for the positive
case, and `NO_DATA` with an empty result set and explicit fallback for the
negative case. A missing or unreachable runtime is a failed smoke test.

## Tests

Tests inject fake Bedrock and OpenSearch clients and make no network calls:

```powershell
cd services/rag-ingestion
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
