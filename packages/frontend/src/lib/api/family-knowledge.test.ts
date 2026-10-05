import { afterEach, expect, it, vi } from 'vitest';
import { askFamilyKnowledge } from './family-knowledge';
import { FamilyDataRedlineError } from './family-guard';

const source = {
  title: 'Synthetic official guide',
  url: 'https://www.mohw.gov.tw/guide',
  locator: 'p. 3',
  current_status: 'current',
};
const answer = { status: 'ANSWER', answer: 'Synthetic answer', sources: [source] };
const config = { apiBaseUrl: '/backend/core/' };
function serve(data: unknown) {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({
          data,
          meta: {
            correlation_id: 'test',
            timestamp: '2026-10-05T00:00:00Z',
            schema_version: '1.0',
          },
        }),
        { status: 200 },
      ),
    );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
afterEach(() => { vi.unstubAllGlobals(); });

it('sends only question and language and preserves official citations', async () => {
  const fetch = serve(answer);
  expect(await askFamilyKnowledge(config, '申請長照', 'zh-TW')).toEqual(answer);
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
    question: '申請長照',
    language: 'zh-TW',
  });
});
it('checks restricted fields before projection, including nested sources', async () => {
  serve({ ...answer, sources: [{ ...source, internal_note: 'private-value' }] });
  await expect(askFamilyKnowledge(config, 'test', 'en-US')).rejects.toThrow(FamilyDataRedlineError);
});
it.each([
  { ...answer, elder_id: 'private' },
  { ...answer, sources: [] },
  { ...answer, status: 'NO_DATA' },
  { ...answer, status: 'PUBLISHED' },
  { ...answer, answer: ' ' },
  { ...answer, sources: [{ ...source, url: 'javascript:alert(1)' }] },
  { ...answer, sources: [{ ...source, url: 'https://www.mohw.gov.tw.example.com/' }] },
  { ...answer, sources: [{ ...source, url: 'https://secret@www.mohw.gov.tw/' }] },
  { ...answer, sources: [{ ...source, url: 'https://www.mohw.gov.tw\\@evil.example/' }] },
])('rejects malformed or unsafe public answers %#', async (data) => {
  serve(data);
  await expect(askFamilyKnowledge(config, 'test', 'en-US')).rejects.toThrow();
});
it.each(['PARTIAL', 'NO_DATA', 'CLARIFY', 'BLOCKED', 'UNAVAILABLE'])(
  'accepts the %s state without treating it as a report',
  async (status) => {
    const data = { ...answer, status, sources: status === 'PARTIAL' ? [source] : [] };
    serve(data);
    expect(await askFamilyKnowledge(config, 'test', 'en-US')).toEqual(data);
  },
);
