# RAG PDF layout repair — 2026-10-06

This records the pre-provider 657-chunk candidate merged in PR #73. The subsequent [v009 rollout](rag-v009-rollout-20261006.md) replaces it with a token-safe 713-chunk candidate; its import and runtime status supersede the statements below. The original validation file remains historical evidence.

55 chunks previously excluded by the grounded-answer layout guard have been rebuilt into 54 complete source units. The local v009 candidate contains 657 chunks: 603 unchanged and 54 replacements. The current development runtime remains `knowledge-v008-aae34e5095e6`; v009 has no new embeddings, database import, or activation.

The candidate is `knowledge-v009-c33f6b2199e7`, with chunk-file SHA-256 `c33f6b2199e769e35fc0f33a8453863ee9dbe7b478dd072c8e4ccc6215d5dee4`. Local output is `.rag-work/layout-v009-final-20261006/`. [Validation results](rag-pdf-layout-validation-20261006.json) record the actual v008 baseline, candidate counts, policy admission, local Core loading, and synthetic citation checks.

## Scope and behavior

The affected sources are 48 chunks from the 2023-07-19 A unit case manager manual appendix and seven from the 114年7月 family caregiver support service manual. They were already admissible to `care_professional` for `general_information`; their flattened PDF columns made the evidence unsafe to pass to generation.

The repair uses source-bound PDF coordinates rather than asking a model to recover column order. It preserves official wording, identifiers, numbers, punctuation, field relationships, page references, and original source metadata. Blank fields stay blank; data cells are never forward-filled. Multi-page course and professional-service tables remain in complete original semantic groups. One family dialogue row previously split between two chunks is now one complete unit, accounting for the change from 658 to 657 total chunks.

The runtime `has_ambiguous_columns` guard and all admission rules remain unchanged. Existing audience/purpose, risk, stop, assessment, currency, license and classification metadata are retained; repaired chunks stay `review_status=needs_review` and `human_source_review=not_completed`.

## Source fidelity

[Source package and rebuild commands](../../data/rag-layout/v001/README.md) include both frozen PDF hashes, parent text hashes, extraction coordinates, explicit diagram topology, expected labels/headers, and controlled omissions. Raw PDFs and the original v008 data were not edited.

97 relevant physical pages were rendered for inspection. Extraction selects 96 pages because the family group-design paragraph begins on physical page 47; the old chunk's 46–47 range also included preceding material from page 46. The original range is preserved, and the new locator states the extracted page.

All selected tables pass exact assignment of substantive PDF glyphs to one physical cell. Five open merged cells in A manual evaluation tables on pages 146–150 use explicit visually checked closures whose text must match the PDF. The continuation table on page 233 inherits headers only from the verified preceding table on page 232. Phantom header subdivisions are resolved through body geometry and strict expected headers.

Seven reconstructed diagrams preserve node labels, edges, cycles, and notes; all substantive glyphs in their selected scopes are assigned once. Two blocks remain excluded and are listed in each relevant difference record:

- A manual page 111 organization diagram: the dotted external-supervisor relation is unresolved; usable job-description prose remains.
- Family manual page 54 resource inventory form: the form is empty; usable surrounding narrative remains.

This is extraction validation and targeted visual inspection. It is not completed human source review, current-law verification, or measured semantic answer accuracy.

## Validation

The actual local candidate passes the existing Core loader for all 657 records. Every one of its 54 replacement units passes the unchanged grounded-answer layout guard and an offline synthetic answer envelope with a source-derived quote span. The latter verifies context construction and citation anchoring; it does not test whether generated claims follow from the source.

| General-information audience | v008 policy-admitted / layout-excluded | v009 policy-admitted / layout-excluded |
| --- | --- | --- |
| elder | 97 / 0 | 97 / 0 |
| family_caregiver | 136 / 0 | 136 / 0 |
| care_professional | 464 / 55 | 463 / 0 |
| system_admin | 50 / 0 | 50 / 0 |

Whole-corpus layout exclusions change from 70 to 15. The remaining 15 are outside this repair's admitted professional scope. Counts describe offline admission/layout checks, not live retrieval results.

The real v008 complete cache validates 603 available vectors for unchanged text. 54 unique new embeddings are required using the existing `gemini-embedding-001` profile. These vectors have not been generated.

Local checks completed:

- 39 focused repair/extractor tests pass, covering merged/empty cells, dropped or duplicated glyphs, diagram references, stale hashes, source/page scope, changed audiences, unchanged records, strict schema, dry-run and output preservation.
- 53 existing preparation/compiler tests passed during this task; final changes were rechecked with the focused suite.
- 28 CI impact-rule tests pass; contract validation and Ruff lint/format pass.
- Extraction was rebuilt with `pdfplumber-0.11.9` and was byte-identical; candidate writing was also repeated without changing existing output.

No destructive local database tests were run. Disposable database integration and the broader service suites are delegated to the PR's existing Gate 1 workflow.

The first CI run passed 460 RAG tests but rejected a new root `.gitattributes` line because the historical v006 acceptance package binds that file's bytes. The LF rule was moved to `data/rag-layout/.gitattributes`; the root file and archived inventories remain unchanged. This preserves historical validation without creating another audit successor or altering runtime admission.

## Remaining work

Review and merge the code/source package, then separately authorize generation of 54 embeddings and the v009 development import. Before activation, verify counts, hashes and vectors and preserve v008 as the rollback release. After controlled activation, rerun real Hybrid retrieval and the existing natural-language question set with `gemini-3.8-flash`, including table/code questions, role isolation, insufficient-data cases and medical refusals. Earlier sporadic BFF fallback and answer-quality limitations remain open until that verification supplies evidence. Production remains disabled.
