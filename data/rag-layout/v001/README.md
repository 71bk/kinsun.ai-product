# Public PDF layout repair v001

This package rebuilds 55 layout-excluded chunks from two frozen official PDFs into 54 complete semantic units. It contains coordinates and extracted public source text, without embeddings, private elder records, runtime configuration, or database writes.

- `recipes.json`: source PDF hashes, parent text hashes, page/region coordinates, expected headers and diagram labels, explicit edges, and omissions.
- `extraction.jsonl`: one strict `knowledge-layout-extraction-v1` document containing actual PDF cells, diagram labels, notes, and page references. Generated with `pdfplumber==0.11.9`.
- Contract: [knowledge-layout-extraction-v1.schema.json](../../../contracts/schemas/rag/knowledge-layout-extraction-v1.schema.json).
- Results and limitations: [2026-10-06 report](../../../docs/project/rag-pdf-layout-repair-20261006.md).

## Source PDFs

| Source | Frozen version | Physical pages | Official download | SHA-256 |
| --- | --- | --- | --- | --- |
| A unit case manager manual, appendix | 2023-07-19 | 255 | [MOHW PDF](https://www.mohw.gov.tw/dl-84180-6177e26d-51f5-4f0a-ade3-2a80d085f641.html) | `f6c31f2ffafaf4e1b467878231786e08a6f39ce386b503bd02b7741489089f3c` |
| Family caregiver support service manual | 114年7月 | 93 | [MOHW PDF](https://www.mohw.gov.tw/dl-95508-3f7969cf-6c27-413f-b0ed-461c9b4e73da.html) | `c8ca94cfed07239676ce8ade678a2396f768cc347f9b51c714e909d095ecc486` |

The original source-page URLs and versions remain unchanged. A different download must fail its hash check. These frozen sources do not establish current online validity.

## Rebuild locally

Run from the repository root, using a Python environment with `pdfplumber==0.11.9` for the optional PDF extraction step. Substitute local PDF paths; raw PDFs are not part of this package.

```powershell
python scripts/rag/extract_knowledge_layout.py `
  --recipes data/rag-layout/v001/recipes.json `
  --source 'mohw_a_unit_case_manager_manual_appendix_20230719=C:/public-sources/a-manual-20230719.pdf' `
  --source 'mohw_family_caregiver_support_manual_202507=C:/public-sources/family-manual-202507.pdf' `
  --output data/rag-layout/v001/extraction.jsonl
```

The output must be absent or byte-identical. A changed output is rejected. The extractor validates PDF hash/page count, table count/headers, expected node labels, and exact single assignment of substantive glyphs inside each selected table or diagram scope. Manually supplied closures for open table borders must match actual PDF text.

The normal ingestion environment can build a candidate from the checked-in extraction without installing a PDF library:

```powershell
uv run --project services/rag-ingestion python scripts/rag/repair_knowledge_layout.py `
  --baseline .rag-work/knowledge-v008/chunks.jsonl `
  --cache .rag-work/cache/v008-complete-cache.json

uv run --project services/rag-ingestion python scripts/rag/repair_knowledge_layout.py `
  --baseline .rag-work/knowledge-v008/chunks.jsonl `
  --cache .rag-work/cache/v008-complete-cache.json `
  --write --output .rag-work/layout-v009-final-20261006
```

The first command is dry-run. Explicit writing produces only `chunks.jsonl`, `report.json`, and `embedding-plan.json` in a named destination; existing different output is rejected. Parent IDs/text hashes, source versions/URLs, page scope, and metadata compatibility are checked before writing. Omit `--cache` when unavailable; potential text reuse then does not count as available vectors.

## Fidelity and exclusions

Each table record retains its headers and complete cells. A merged cell is repeated only where its physical rectangle spans a row. Empty codes or assessment fields stay empty. Original semantic groups remain intact across page boundaries; family manual page 31 merges two previous chunks that split the same dialogue row. No global whitespace removal, NFKC conversion, guessed data continuation, or model-based PDF repair is used.

Seven diagrams retain actual labels, recorded edges/cycles, and attached notes. Two blocks are explicitly omitted: the A manual page 111 organization diagram has an unresolved dotted relation; family manual page 54 contains an empty resource inventory form. Their usable surrounding prose remains. Family parent `..._0073` retains its original 46–47 page range, while the repaired group-design unit is correctly extracted from physical page 47.

All new records retain `needs_review` / `not_completed`, existing policy and license/classification metadata, and `production_approved=false` / `activation_allowed=false`. This package provides a local candidate; import, provider calls, activation, answer-quality evaluation, and production approval are separate operations.
