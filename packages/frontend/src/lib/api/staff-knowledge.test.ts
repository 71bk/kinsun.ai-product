import { afterEach, expect, it, vi } from 'vitest';
import { askStaffKnowledge } from './staff-knowledge';
import { FamilyDataRedlineError } from './family-guard';
afterEach(() => {
  vi.unstubAllGlobals();
});
it('posts only the question and language to the staff endpoint', async () => {
  const data = { status: 'NO_DATA', answer: 'Synthetic fallback', sources: [] };
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
  expect(await askStaffKnowledge({ apiBaseUrl: '/backend/core/' }, 'Question', 'en-US')).toEqual(
    data,
  );
  expect(String(fetch.mock.calls[0][0])).toContain('/api/v1/staff/knowledge/questions');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
    question: 'Question',
    language: 'en-US',
  });
});
it('rejects private record fields even for professionals in this public entry', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            data: { status: 'NO_DATA', answer: 'Synthetic', sources: [], transcript: 'private' },
            meta: {
              correlation_id: 'test',
              timestamp: '2026-10-05T00:00:00Z',
              schema_version: '1.0',
            },
          }),
          { status: 200 },
        ),
      ),
  );
  await expect(
    askStaffKnowledge({ apiBaseUrl: '/backend/core/' }, 'Question', 'en-US'),
  ).rejects.toThrow(FamilyDataRedlineError);
});
