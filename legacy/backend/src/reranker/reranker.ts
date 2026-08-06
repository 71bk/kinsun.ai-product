import type { PersonaContext, RankedResult, RankingFactors, SearchResult } from '@elderly-care/shared';

const SOURCE_CREDIBILITY_BY_AGENCY: Record<string, number> = {
  衛生福利部: 1.0,
  國民健康署: 1.0,
  疾病管制署: 0.95,
};
const DEFAULT_SOURCE_CREDIBILITY = 0.7;

const WEIGHTS = {
  queryRelevance: 0.4,
  sourceCredibility: 0.2,
  personaApplicability: 0.15,
  recency: 0.15,
  reviewStatus: 0.1,
} as const;

function normalize(values: number[]): (v: number) => number {
  const max = Math.max(0, ...values);
  return (v: number) => (max > 0 ? v / max : 0);
}

function recencyScore(effectiveDate: string, now: Date): number {
  const ageDays = (now.getTime() - new Date(effectiveDate).getTime()) / (1000 * 60 * 60 * 24);
  if (Number.isNaN(ageDays) || ageDays < 0) return 1;
  // Decays toward 0 over ~5 years; recent documents score close to 1.
  return Math.max(0, 1 - ageDays / (365 * 5));
}

function personaApplicability(_result: SearchResult, _persona: PersonaContext | undefined): number {
  // Persona has no region/service-type field yet, so every document is
  // equally applicable today; this hook lets that signal plug in once
  // Persona gains one, without changing the Reranker's call sites.
  return 1;
}

/**
 * Reranker (E04) — combines relevance/credibility/applicability/recency/
 * review-status into one score per design.md's RankingFactors shape, then
 * (via topN) truncates to the caller's requested count. Every factor is
 * recorded on the result so the ranking is reproducible/auditable (E04.3).
 */
export class Reranker {
  rerank(_query: string, results: SearchResult[], persona?: PersonaContext, now: Date = new Date()): RankedResult[] {
    const relevanceNormalizer = normalize(results.map((r) => r.combinedScore));

    const ranked: RankedResult[] = results.map((result) => {
      const factors: RankingFactors = {
        queryRelevance: relevanceNormalizer(result.combinedScore),
        sourceCredibility: SOURCE_CREDIBILITY_BY_AGENCY[result.sourceAgency] ?? DEFAULT_SOURCE_CREDIBILITY,
        personaApplicability: personaApplicability(result, persona),
        recency: recencyScore(result.metadata.effectiveDate, now),
        reviewStatus: result.metadata.reviewStatus === 'approved' ? 1 : 0,
      };
      const rerankScore =
        factors.queryRelevance * WEIGHTS.queryRelevance +
        factors.sourceCredibility * WEIGHTS.sourceCredibility +
        factors.personaApplicability * WEIGHTS.personaApplicability +
        factors.recency * WEIGHTS.recency +
        factors.reviewStatus * WEIGHTS.reviewStatus;

      return { ...result, rerankScore, rankingFactors: factors };
    });

    return ranked.sort((a, b) => b.rerankScore - a.rerankScore);
  }

  /**
   * Property 15 (Top-N 截斷): returns exactly min(n, results.length) items,
   * and they are precisely the n highest-rerankScore items — never an
   * arbitrary subset.
   */
  topN(rankedResults: RankedResult[], n: number): RankedResult[] {
    return [...rankedResults].sort((a, b) => b.rerankScore - a.rerankScore).slice(0, Math.max(0, n));
  }
}
