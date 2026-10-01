# Admission calibration and human review

This is an evaluation-only change. The application still uses its existing Hybrid
ranking, 0.7 admission rule, 50-result search limit, final governance checks and
3–5 citation contract. Neither feature flag nor the v004 release/policy is changed.

## What is included

- `admission-cases-v1.json`: 24 existing knowledge queries, 8 new paraphrases and
  12 near-domain no-answer probes. All 44 questions are synthetic. New paraphrases
  inherit their semantic group's original split: 30 development, 14 holdout.
- Four audiences: elder, family caregiver, care professional and system admin.
  The 176 audience/query trials are correlated; they are not 176 independent questions.
- `reports/admission-snapshot-v1.json`: at most 100 candidates per trial, captured
  through read-only PostgreSQL transactions. Raw lexical and vector scores, Hybrid
  scores, per-candidate final citation/governance eligibility and baseline IDs are saved.
  All 176 baseline searches and final outputs must match the existing adapter/gate.
- `review/admission-review-v1.json`: evidence text and source locators, complete
  pooled judgment slots, the prior 16 missed queries, and separate audience reviews.
  Every human grade, answerability decision and sufficient-evidence set starts pending.
  A focused reading worksheet for the 16 earlier misses is available at
  [review/admission-missed-cases-v1.md](review/admission-missed-cases-v1.md).
- `reports/admission-comparison-v1.json`: the existing rule and eight raw-score
  combinations, with Hybrid order and the 3–5 citation rule fixed. Only development
  is swept. Holdout is reported for the existing baseline only.

Measured results and their limitations: [admission-summary-v1.md](reports/admission-summary-v1.md).

The new questions were written by the same implementer with knowledge of the old
results. They are challenge/regression samples, **not independently collected or
blind validation**. An independent reviewer must still supply fresh validation data.

## Reproduce

Run from the repository root. Every output must use a new path; existing reports
and review work are never overwritten. Capture loads the configured staging provider,
may call Google embeddings on cache misses (at most one per query), reads the public
RAG data plane, and has a 15-minute deadline. No answers, personal records, database
writes, migrations or activation are involved. The checked-in snapshot avoids all
provider and network access for review and comparison.

```powershell
# Explicit live capture; use a new versioned path when repeating.
services/agent-runtime/.venv/Scripts/python.exe -B scripts/rag/evaluate_admission.py capture --output evals/rag/reports/admission-snapshot-v2.json

# Offline: prepare a fresh review copy from the checked-in snapshot.
services/rag-ingestion/.venv/Scripts/python.exe -B scripts/rag/evaluate_admission.py review --snapshot evals/rag/reports/admission-snapshot-v1.json --output .qa/admission-human-review.json

# Offline: compare after editing that review copy, or use the pending template.
services/rag-ingestion/.venv/Scripts/python.exe -B scripts/rag/evaluate_admission.py compare --snapshot evals/rag/reports/admission-snapshot-v1.json --review .qa/admission-human-review.json --output .qa/admission-human-comparison.json
```

The snapshot pins dataset, corpus manifest, profile and policy bytes. Review files
bind to the exact snapshot SHA-256, case list and public evidence text. Source
versions are the pinned corpus versions, not a new assertion about current law.
The capture records code hashes and its time window. SQL timing is diagnostic only,
with embedding timing recorded separately; this is not voice/answer end-to-end latency.

## Human review procedure

Start with the 16 entries whose `previous_miss_stage` is populated. For each question:

1. Read the requested detail and the full evidence text under `evidence[chunk_id]`.
   A law mentioning a service is not automatically enough to answer an application
   process, a specific fee, a provider recommendation or a personal eligibility question.
2. Fill every `qrels[chunk_id].grade` in its pool: **0** irrelevant, **1** background,
   **2** directly supporting part of the answer, **3** directly answering the requested
   detail. `null` means unjudged, never irrelevant. Draft anchor grades are suggestions
   with preserved provenance; only `grade` is the reviewer's judgment.
3. Review answerability separately for each audience. Consult that audience's
   snapshot governance states; blocked evidence must not justify an authorized answer.
   Record `answerable`, a rationale, and each alternative minimal `sufficient_sets`
   of 1–5 supporting IDs (grades 2 or 3). A pair means both pieces are required;
   two separate singleton sets mean either piece suffices. For no answer, use `false`
   and an empty list, explaining what necessary information is missing.
4. Complete `reviewer`, timezone-qualified ISO `reviewed_at`, and set `status` to
   `REVIEWED` only after all pooled grades are filled. Automated tooling cannot
   certify that an attribution is authentic; reviewer identity and independence
   must also be confirmed by the owner outside this file.

The shared qrels measure semantic relevance; audience-specific permission and
answerability are distinct. If relevance itself changes materially by audience,
keep that review pending and create separate audience-specific questions in a
successor dataset rather than overwriting a shared judgment.

The pool contains the captured candidates across four audiences plus draft law
anchors. It is not exhaustive corpus-wide relevance. An anchor absent from a
particular audience's captured pool has no captured eligibility proof for that
audience; review additional source/governance evidence before approving it.

## Interpreting the comparison

The baseline admits a candidate if Hybrid score ≥0.7 **or** raw vector score ≥0.7
**or** raw lexical score ≥0.7. Candidate experiments omit the Hybrid score from
admission, varying raw vector floors (0.50, 0.60, 0.70, 0.80) and raw lexical floors
(0.5, 0.7) separately. These scales are not interchangeable confidence probabilities.
The experiments keep sorting by the same Hybrid score and retain all eligibility
and citation checks, including invalid-citation failure before the fifth result.

- Draft anchor recall and draft negative acceptance are diagnostic only.
  The latter measures evidence acceptance under forced retrieval, not actual wrong
  answers: the application router may reject a private/safety query before searching.
- Reviewed missed-answer and false-acceptance rates use explicit reviewed denominators.
  Zero reviewed examples produce `null`, not 0% error or a passing grade.
- Reviewed pooled Recall/NDCG describe the labeled pool, not the entire corpus.
- `one_or_two_governed_count_only_opportunities` counts cases blocked by the current
  minimum. It does not simulate a safe 1–5 contract or prove that one citation suffices.
- No policy is automatically selected or activated, even after filling the template.

After independent review, choose a candidate using development results and a written
false-acceptance tolerance, freeze its parameters and evidence hashes, then validate
that single candidate on separately supplied, independently authored questions.
Do not sweep this holdout to choose a winner. A future 1–5 contract requires a separate
spec/schema/prompt/fallback change and answer claim/citation review.

## Attestation

Audit v013 binds the tools, dataset, snapshot, pending review template and comparison.
All predecessor package bytes remain sealed. Edit a separate review copy; publishing
reviewed evidence requires a successor package. Byte integrity is not human relevance
review, generated-answer acceptance or production approval.
