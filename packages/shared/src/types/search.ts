export interface MetadataFilter {
  sourceAgency?: string[];
  serviceType?: string[];
  region?: string[];
  effectiveDateAfter?: string;
  riskLevel?: string[];
  reviewStatus: 'approved';
}

export interface DocumentMetadata {
  sourceAgency: string;
  serviceType: string;
  region: string;
  effectiveDate: string;
  expiryDate: string | null;
  riskLevel: string;
  reviewStatus: 'needs_review' | 'approved' | 'rejected';
  version: string;
}

export interface SearchQuery {
  originalQuestion: string;
  reformulatedQuery: string;
  filters: MetadataFilter;
  topK: number;
}

export interface SearchResult {
  chunkId: string;
  documentId: string;
  content: string;
  sourceAgency: string;
  documentTitle: string;
  publishDate: string;
  bm25Score: number;
  vectorScore: number;
  combinedScore: number;
  metadata: DocumentMetadata;
}

export interface RankingFactors {
  queryRelevance: number;
  sourceCredibility: number;
  personaApplicability: number;
  recency: number;
  reviewStatus: number;
}

export interface RankedResult extends SearchResult {
  rerankScore: number;
  rankingFactors: RankingFactors;
}
