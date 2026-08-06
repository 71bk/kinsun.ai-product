import { describe, expect, it } from 'vitest';
import type { LlmGenerateRequest } from './types.js';
import { buildUserMessage } from './message-builder.js';

const baseRequest: LlmGenerateRequest = {
  systemPrompt: 'sys',
  persona: {
    displayName: '林阿嬤',
    preferredLanguage: 'nan-TW',
    responseLength: 'short',
    speakingSpeed: 'normal',
    interactionStyle: 'warm',
    customGreeting: '',
  },
  currentUtterance: '我今天吃了地瓜稀飯',
  confirmedMemories: [],
  recentSummary: null,
  situationalContext: {
    currentTime: '2026-07-24T09:00:00Z',
    dayOfWeek: 'Friday',
    weather: null,
    recentInteractionCount: 1,
    lastInteractionTime: null,
  },
  searchResults: null,
  conversationHistory: [],
};

describe('buildUserMessage', () => {
  it('always includes the elder utterance', () => {
    const message = buildUserMessage(baseRequest);
    expect(message).toContain('我今天吃了地瓜稀飯');
  });

  it('frames confirmed memories as reference, not asserted fact', () => {
    const message = buildUserMessage({
      ...baseRequest,
      confirmedMemories: [
        {
          memoryId: 'm1',
          elderId: 'e1',
          category: 'preference',
          content: '喜歡喝烏龍茶',
          confirmedBy: 'cg1',
          confirmedAt: '2026-01-01T00:00:00Z',
          sourceConversationId: 'c1',
          isActive: true,
          lastUsedAt: null,
        },
      ],
    });
    expect(message).toContain('喜歡喝烏龍茶');
    expect(message).toContain('僅供參考');
  });

  it('includes search results with source attribution when present', () => {
    const message = buildUserMessage({
      ...baseRequest,
      searchResults: [
        {
          chunkId: 'c1',
          documentId: 'd1',
          content: '每日應攝取足夠水分',
          sourceAgency: '衛生福利部',
          documentTitle: '長者衛教手冊',
          publishDate: '2026-01-01',
          bm25Score: 1,
          vectorScore: 1,
          combinedScore: 1,
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
        },
      ],
    });
    expect(message).toContain('長者衛教手冊');
    expect(message).toContain('衛生福利部');
    expect(message).toContain('僅供參考不作為醫療診斷依據');
  });

  it('omits the memory/search sections entirely when there is nothing to include', () => {
    const message = buildUserMessage(baseRequest);
    expect(message).not.toContain('已知資訊');
    expect(message).not.toContain('相關衛教資訊');
  });
});
