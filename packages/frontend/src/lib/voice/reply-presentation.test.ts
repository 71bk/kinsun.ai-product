import { describe, expect, it } from 'vitest';

import { companionReplyForSpeech, presentCompanionReply } from './reply-presentation';

const citedReply = `先說結論，三餐要盡量包含不同類食物。
• 每餐選擇原型食物。
• 吃不多時可以少量多餐。

引用來源：
- [國民健康署《老年期營養手冊》，p. 21](https://example.test/guide)
- [國民健康署《我的餐盤》](https://example.test/plate)`;

describe('RAG reply presentation', () => {
  it('separates the readable answer from canonical citations', () => {
    expect(presentCompanionReply(citedReply)).toEqual({
      body: `先說結論，三餐要盡量包含不同類食物。
• 每餐選擇原型食物。
• 吃不多時可以少量多餐。`,
      citations: [
        {
          label: '國民健康署《老年期營養手冊》，p. 21',
          href: 'https://example.test/guide',
        },
        {
          label: '國民健康署《我的餐盤》',
          href: 'https://example.test/plate',
        },
      ],
    });
  });

  it('does not send citation labels or URLs to text to speech', () => {
    expect(companionReplyForSpeech(citedReply)).toBe(
      `先說結論，三餐要盡量包含不同類食物。
• 每餐選擇原型食物。
• 吃不多時可以少量多餐。`,
    );
  });

  it('keeps malformed source text visible instead of silently dropping it', () => {
    const malformed = '回答內容\n\n引用來源：\n- 來源格式已改變';

    expect(presentCompanionReply(malformed)).toEqual({ body: malformed, citations: [] });
  });
});
