# Public RAG routing and retrieval quality

This suite separates Core routing, candidate retrieval, score admission, citation
governance, and the final minimum-three-results contract. All questions are
synthetic. Evidence anchors were drafted from the pinned corpus, not from search
results, and **still require independent human review**.

## Inputs and interpretation

- `cases-v1.json`: 40 semantic groups × 3 paraphrases = 120 cases. All variants of
  a group stay in one split: 81 development / 39 holdout. This is a reproducible
  regression split, not an independently collected or blinded test population.
- Source locators resolve to v004 storage IDs. Runtime policy translates these
  to v003 citation IDs; these identities are deliberately reported separately.
- Only 66 questions have law-article evidence anchors. The anchors are not
  exhaustive relevance judgments; `anchor_recall_at_5` and `anchor_ndcg_at_5`
  must not be presented as corpus-wide Recall@5/NDCG@5 or a production quality gate.
- Nutrition/application cases are coverage probes, without invented positive
  labels on a document's first chunk. Companion/private/safety cases test routing;
  forcing them through retrieval is diagnostic only, not the application flow.
- A missing denominator yields null. `INSUFFICIENT` means 1–2 governed results;
  the real runtime returns `NO_DATA` and exposes none of them to the model.
- Retrieved citation metadata may say `verified` because of the policy overlay;
  it does not mean the storage release is production-approved or that answers
  have been independently judged. Neither is true here.

## Offline, no credentials or API calls

From the repository root (PowerShell):

```powershell
services/core-api/.venv/Scripts/python.exe scripts/rag/evaluate_quality.py --output evals/rag/reports/routing-v1.json
```

Core unit tests automatically validate routing accuracy ≥90%, knowledge recall
≥95%, and nonknowledge false positives ≤5% on each grouped split, as well as
dataset integrity, unique source anchors and ranking metric denominators.
Agent unit tests exercise normalization, ranking replay bounds, and the complete
runtime governance/citation suite. `evals/rag/` changes select the RAG CI jobs.
CI never runs the live evaluator or loads live provider credentials for these tests.

## Explicit live evaluation

```powershell
services/agent-runtime/.venv/Scripts/python.exe scripts/rag/evaluate_live_quality.py --output evals/rag/reports/live-retrieval-v1.json
```

This loads the configured staging factory, pins v004 release/profile/policy and
profile weights, uses Google query embeddings, and reads PostgreSQL. The database
connection and diagnostic transaction are read-only. No generation, database
writes, migrations, production activation, or personal records are involved.
Default: the first variant of all 40 groups; `--all-variants`: all 120 questions.
Each embedding has a 35-second limit and the run has a 15-minute limit.

Synthetic query embeddings are cached under `.qa/rag-quality-embeddings-v1.json`,
bound to the embedding config/profile and keyed by query SHA-256. The cache is
local and not committed. The reported call count is for that invocation; it is
not a monetary cost estimate. There is no automatic retry on failure. A failed
invocation does not replace the previous successful report.

The diagnostic query reuses the exact runtime eligibility predicates and 50-per-leg
candidate bounds. It returns at most 100 candidates to the evaluator, which
compares Hybrid, lexical, dense, equal-weight Hybrid, raw-floor Hybrid and RRF.
Every original query's Hybrid replay must match the real backend's ranked IDs.
All strategies use the same final audience/purpose/hash/citation gate and the
existing minimum-three-results rule. No diagnostic row enters Agent context.

RRF uses `sum(1 / (60 + rank))`. Its rank score is **not** tested against the 0.7
Hybrid floor; the experiment uses the existing raw-evidence floor for admission.
This comparison changes both admission and ranking versus baseline, so also
compare `raw_floor` versus `rrf` to isolate ranking. See the
[official RRF formula](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion).
The lexical leg is PostgreSQL FTS/trigram, not BM25 or learned sparse embeddings.

## Rollout and rollback

- Core: `KNOWLEDGE_ROUTER_V2_ENABLED=true` selects the structured deterministic
  router. It emits version/reason/purpose logs without input text. `false` restores
  the exact old classifier. Restart Core after changing process configuration.
- Agent: `RAG_QUERY_NORMALIZATION_ENABLED=true` enables legal numeral/full-width
  normalization for V2 retrieval. `false` restores existing query behavior.
  This flag remains off because the live comparison did not improve overall ranking.
- Both defaults are false. No running service or real `.env` was changed.
- Ranking alternatives are evaluation-only. No RRF, sparse encoder, reranker,
  lower score threshold, candidate-pool expansion, or minimum-count change was
  activated. All existing consent, scope and production gates remain enforced.

## Promotion gates still outstanding

Independent review must confirm relevance labels and source coverage before
changing score thresholds or the 3–5 citation contract. Add near-domain negatives,
an independent paraphrase sample, all four audiences, graded alternative evidence,
and generated-answer claim/citation checks. Report answer grounding and unsupported
claim rates only after those checks actually run; this suite does not estimate them.
Browser E2E, isolated DB integration, and production approval remain separate gates.

Current implementation byte attestation is `audits/v011/preflight`, validated by
`scripts/rag/quality_audit.py validate`. Audits v009/v010 are sealed historical
evidence. None of these byte attestations constitutes relevance acceptance.
