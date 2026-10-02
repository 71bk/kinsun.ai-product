# Admission evaluation: historical baseline and current scope

As of 2026-10-02, phase 1 retires the mandatory manual-review development
workflow. Users need not fill all 1,055 qrels, and the standalone answer-evidence
review UI/workbook entry points are retired. Code is versioned by Git; no current
byte audit successor, audit v021 or repeated snapshot/archive chain is required.
See [phase 1 record](../../docs/project/rag-simplification-phase1-20261002.md).

The checked-in v1 dataset, snapshot, review template, comparison and summary are
historical evidence. Preserve their pinned bytes. Audit v013 and its successors
attest their original captures only; they do not certify current code or create
a new successor obligation. Historical documents prescribing exhaustive manual
review or per-change sealed packages are superseded by this instruction.

## What the historical baseline means

The 44 synthetic questions comprise 30 development and 14 holdout cases. Four
audiences produce 176 correlated trials, not 176 independent questions. The
snapshot records captured candidates, scores and final eligibility for its
pinned corpus/profile/policy versions. The implementer authored the challenge
questions with knowledge of prior results, so these are regression samples,
not independently collected or blind validation.

[The historical summary](reports/admission-summary-v1.md) reports those results.
Unjudged `null` means unjudged; zero reviewed examples produce no reviewed error
rate, not a passing grade. Draft anchors, AI assessments, byte hashes and
synthetic tests do not establish authentic human review or production approval.
Do not change pending/needs_review records to human `verified` without real review.

## Current runtime boundary and next work

Phase 1 does not change Hybrid ranking, the existing 0.7 admission rule,
50-result search limit, final governance checks, citation contract, runtime flags
or the v004 release/policy. The baseline comparison keeps ranking and governance
fixed; its raw score scales are not confidence probabilities. Historical
one/two-citation opportunity counts do not prove answer sufficiency.

Phase 2 simplifies data-pipeline/admission metadata, consolidates 735 candidates
and implements content-hash reuse and automatic source/content validation. Phase 3
adjusts runtime and SQL together for natural-question Hybrid RAG, removing exact
question matching, manual support sets, fixed answers and the three-citation
minimum. Phase 4 evaluates real questions; import/environment switching and rollback
follow only with authorization. These are planned changes, not completed behavior.
Preserve source/data versions and embedding content hashes throughout;
measure answer support honestly without turning exhaustive human labels into a
routine development prerequisite. Any future live capture must respect provider,
read-only/public-data and external-action authorization boundaries; local
regression checks alone do not authorize database writes or activation.
