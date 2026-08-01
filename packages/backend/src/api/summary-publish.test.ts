import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, GetCommand, PutCommand, QueryCommand } from '@aws-sdk/lib-dynamodb';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import type { SummaryRecord } from '@elderly-care/shared';

const docClient = DynamoDBDocumentClient.from(new DynamoDBClient({}));
const ddbMock = mockClient(docClient);

vi.mock('../db/client.js', async () => {
  const actual = await vi.importActual<typeof import('../db/client.js')>('../db/client.js');
  return {
    ...actual,
    DynamoTable: class extends actual.DynamoTable {
      constructor() {
        super(undefined, docClient);
      }
    },
  };
});

const { handler: publishHandler } = await import('./summary-publish.js');
const { handler: withdrawHandler } = await import('./summary-withdraw.js');
const { listSummariesHandler } = await import('./summaries.js');

function fakeEvent(
  overrides: Partial<APIGatewayProxyEvent>,
  authorizer: Record<string, unknown> = { userId: 'cg1', role: 'caregiver', tenantId: 't1', authorizedElderIds: 'elder-1' },
): APIGatewayProxyEvent {
  return {
    body: null,
    headers: {},
    pathParameters: null,
    queryStringParameters: null,
    requestContext: { authorizer } as never,
    ...overrides,
  } as APIGatewayProxyEvent;
}

const draftSummary: SummaryRecord = {
  PK: 'ELDER#elder-1',
  SK: 'SUM#2026-07-24',
  summaryId: 'sum-1',
  elderId: 'elder-1',
  date: '2026-07-24',
  content: {
    overview: '今天狀況良好',
    meals: [],
    activities: [],
    sleep: null,
    medicationStatements: [],
    importantEvents: [],
    emotionalState: null,
  },
  sourceEventIds: ['evt-1'],
  generatedAt: '2026-07-24T00:00:00Z',
  version: 1,
  ttl: 0,
  status: 'draft',
  publishedAt: null,
  publishedBy: null,
};

describe('summary-publish handler', () => {
  beforeEach(() => {
    ddbMock.reset();
  });

  it('rejects a family member trying to publish', async () => {
    const res = await publishHandler(
      fakeEvent(
        { pathParameters: { elderId: 'elder-1', date: '2026-07-24' } },
        { userId: 'fm1', role: 'family', tenantId: 't1', authorizedElderIds: 'elder-1' },
      ),
    );
    expect(res.statusCode).toBe(403);
  });

  it('returns 404 when no summary exists for that date', async () => {
    ddbMock.on(GetCommand).resolves({ Item: undefined });
    const res = await publishHandler(fakeEvent({ pathParameters: { elderId: 'elder-1', date: '2026-07-24' } }));
    expect(res.statusCode).toBe(404);
  });

  it('flips a draft summary to published and stamps publishedAt/publishedBy', async () => {
    ddbMock.on(GetCommand).resolves({ Item: draftSummary });
    ddbMock.on(PutCommand).resolves({});

    const res = await publishHandler(fakeEvent({ pathParameters: { elderId: 'elder-1', date: '2026-07-24' } }));

    expect(res.statusCode).toBe(200);
    const saved = ddbMock.commandCalls(PutCommand)[0]!.args[0].input.Item as SummaryRecord;
    expect(saved.status).toBe('published');
    expect(saved.publishedBy).toBe('cg1');
    expect(saved.publishedAt).toBeTruthy();
  });
});

describe('summary-withdraw handler', () => {
  beforeEach(() => {
    ddbMock.reset();
  });

  it('flips a published summary to withdrawn but keeps publish history', async () => {
    const published: SummaryRecord = { ...draftSummary, status: 'published', publishedAt: '2026-07-24T01:00:00Z', publishedBy: 'cg1' };
    ddbMock.on(GetCommand).resolves({ Item: published });
    ddbMock.on(PutCommand).resolves({});

    const res = await withdrawHandler(fakeEvent({ pathParameters: { elderId: 'elder-1', date: '2026-07-24' } }));

    expect(res.statusCode).toBe(200);
    const saved = ddbMock.commandCalls(PutCommand)[0]!.args[0].input.Item as SummaryRecord;
    expect(saved.status).toBe('withdrawn');
    expect(saved.publishedAt).toBe('2026-07-24T01:00:00Z');
    expect(saved.publishedBy).toBe('cg1');
  });
});

describe('listSummariesHandler — family visibility gate', () => {
  beforeEach(() => {
    ddbMock.reset();
  });

  it('hides a draft summary from a family member', async () => {
    ddbMock.on(QueryCommand).resolves({ Items: [draftSummary] });
    const res = await listSummariesHandler(
      fakeEvent(
        { pathParameters: { elderId: 'elder-1' } },
        { userId: 'fm1', role: 'family', tenantId: 't1', authorizedElderIds: 'elder-1' },
      ),
    );
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).items).toHaveLength(0);
  });

  it('shows a published summary to a family member', async () => {
    const published: SummaryRecord = { ...draftSummary, status: 'published', publishedAt: '2026-07-24T01:00:00Z', publishedBy: 'cg1' };
    ddbMock.on(QueryCommand).resolves({ Items: [published] });
    const res = await listSummariesHandler(
      fakeEvent(
        { pathParameters: { elderId: 'elder-1' } },
        { userId: 'fm1', role: 'family', tenantId: 't1', authorizedElderIds: 'elder-1' },
      ),
    );
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).items).toHaveLength(1);
  });

  it('shows both draft and published summaries to the caregiver', async () => {
    ddbMock.on(QueryCommand).resolves({ Items: [draftSummary] });
    const res = await listSummariesHandler(fakeEvent({ pathParameters: { elderId: 'elder-1' } }));
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).items).toHaveLength(1);
  });

  it('shows a withdrawn summary to family as a redacted placeholder, not hidden entirely (IA doc §7.3)', async () => {
    const withdrawn: SummaryRecord = {
      ...draftSummary,
      status: 'withdrawn',
      publishedAt: '2026-07-24T01:00:00Z',
      publishedBy: 'cg1',
      content: { ...draftSummary.content, overview: '曾經發布過的內容' },
      sourceEventIds: ['evt-1', 'evt-2'],
    };
    ddbMock.on(QueryCommand).resolves({ Items: [withdrawn] });
    const res = await listSummariesHandler(
      fakeEvent(
        { pathParameters: { elderId: 'elder-1' } },
        { userId: 'fm1', role: 'family', tenantId: 't1', authorizedElderIds: 'elder-1' },
      ),
    );
    expect(res.statusCode).toBe(200);
    const items = JSON.parse(res.body).items;
    expect(items).toHaveLength(1);
    expect(items[0].status).toBe('withdrawn');
    expect(items[0].content.overview).toBe('');
    expect(items[0].sourceEventIds).toEqual([]);
  });

  it('caregiver still sees the withdrawn summary content untouched', async () => {
    const withdrawn: SummaryRecord = { ...draftSummary, status: 'withdrawn', content: { ...draftSummary.content, overview: '曾經發布過的內容' } };
    ddbMock.on(QueryCommand).resolves({ Items: [withdrawn] });
    const res = await listSummariesHandler(fakeEvent({ pathParameters: { elderId: 'elder-1' } }));
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).items[0].content.overview).toBe('曾經發布過的內容');
  });
});
