import { describe, expect, it } from 'vitest';
import type { SearchResult } from '@elderly-care/shared';
import type { Bm25SearchAdapter, VectorSearchAdapter } from '../search/adapters.js';
import { SearchEngine } from '../search/engine.js';
import type { QueryReformulator } from '../search/reformulate.js';
import { HealthAnswerGenerator } from '../search/answer.js';

function makeResult(overrides: Partial<SearchResult>): SearchResult {
  return {
    chunkId: 'chunk-1',
    documentId: 'doc-1',
    content: '長者每日應攝取足夠水分，建議每天至少 1500 毫升。',
    sourceAgency: '衛生福利部',
    documentTitle: '長者衛教手冊',
    publishDate: '2026-01-01',
    bm25Score: 5,
    vectorScore: 0.8,
    combinedScore: 5.8,
    metadata: {
      sourceAgency: '衛生福利部',
      serviceType: 'health',
      region: 'TW',
      effectiveDate: '2026-01-01',
      expiryDate: null,
      riskLevel: 'low',
      reviewStatus: 'approved',
      version: '1',
    },
    ...overrides,
  };
}

const passthroughReformulator: QueryReformulator = { async reformulate(q) { return q; } };

/**
 * 衛教 RAG 查詢整合測試 (task 25.3). Wires SearchEngine (with fake BM25/
 * vector adapters returning fixture results — some valid, some
 * needs_review or expired) into the real HealthAnswerGenerator, and checks
 * the final grounded answer only ever cites the valid document — i.e. that
 * Property 13's filtering, which SearchEngine applies, is what
 * HealthAnswerGenerator actually receives, not bypassed by the extra
 * composition layer.
 */
describe('Integration: hybrid search -> filtering -> reranking -> grounded answer', () => {
  it('cites only the approved, unexpired document even when the raw fixtures include invalid ones', async () => {
    const validResult = makeResult({ chunkId: 'valid-1' });
    const needsReviewResult = makeResult({
      chunkId: 'needs-review-1',
      documentTitle: '未審核文件',
      metadata: { ...validResult.metadata, reviewStatus: 'needs_review' },
    });
    const expiredResult = makeResult({
      chunkId: 'expired-1',
      documentTitle: '已過期文件',
      metadata: { ...validResult.metadata, expiryDate: '2020-01-01' },
    });

    const bm25Adapter: Bm25SearchAdapter = { async search() { return [validResult, needsReviewResult]; } };
    const vectorAdapter: VectorSearchAdapter = { async search() { return [validResult, expiredResult]; } };

    const searchEngine = new SearchEngine({ bm25Adapter, vectorAdapter, reformulator: passthroughReformulator });

    let capturedContext = '';
    const fakeLlmClient = {
      async send(command: { input: { messages: { content: { text?: string }[] }[] } }) {
        capturedContext = command.input.messages[0]!.content[0]!.text ?? '';
        return {
          output: { message: { content: [{ text: '長者一天建議喝水約 1500 毫升（資料來源：長者衛教手冊／衛生福利部）' }] } },
        };
      },
    };

    const generator = new HealthAnswerGenerator({ searchEngine, llmClient: fakeLlmClient as never });
    const response = await generator.answer('長者一天要喝多少水？');

    expect(response.grounded).toBe(true);
    expect(response.sources).toHaveLength(1);
    expect(response.sources[0]!.chunkId).toBe('valid-1');
    expect(response.disclaimer).toContain('僅供參考');

    // The needs_review/expired documents must never even reach the LLM prompt.
    expect(capturedContext).not.toContain('未審核文件');
    expect(capturedContext).not.toContain('已過期文件');
    expect(capturedContext).toContain('長者衛教手冊');
  });

  it('returns the fixed "don\'t know" answer, skipping the LLM entirely, when every result is filtered out', async () => {
    const needsReviewOnly = makeResult({ metadata: { ...makeResult({}).metadata, reviewStatus: 'needs_review' } });
    const bm25Adapter: Bm25SearchAdapter = { async search() { return [needsReviewOnly]; } };
    const vectorAdapter: VectorSearchAdapter = { async search() { return []; } };
    const searchEngine = new SearchEngine({ bm25Adapter, vectorAdapter, reformulator: passthroughReformulator });

    let llmCalled = false;
    const fakeLlmClient = { async send() { llmCalled = true; return {}; } };

    const generator = new HealthAnswerGenerator({ searchEngine, llmClient: fakeLlmClient as never });
    const response = await generator.answer('這個問題沒有衛教資料');

    expect(response.grounded).toBe(false);
    expect(response.sources).toHaveLength(0);
    expect(llmCalled).toBe(false);
  });
});
