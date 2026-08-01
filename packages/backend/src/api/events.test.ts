import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, GetCommand, PutCommand, QueryCommand } from '@aws-sdk/lib-dynamodb';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { APIGatewayProxyEvent } from 'aws-lambda';
import type { EventRecord } from '@elderly-care/shared';

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

const { listEventsHandler, updateEventHandler } = await import('./events.js');

function fakeEvent(overrides: Partial<APIGatewayProxyEvent>): APIGatewayProxyEvent {
  return {
    body: null,
    headers: {},
    pathParameters: null,
    queryStringParameters: null,
    requestContext: {
      authorizer: { userId: 'cg1', role: 'caregiver', tenantId: 't1', authorizedElderIds: 'elder-1' },
    } as never,
    ...overrides,
  } as APIGatewayProxyEvent;
}

const existingEvent: EventRecord = {
  PK: 'ELDER#elder-1',
  SK: 'EVENT#2026-07-24#evt-1',
  GSI1PK: 'ELDER#elder-1#EVENT_TYPE#meal',
  GSI1SK: '2026-07-24',
  GSI2PK: 'ELDER#elder-1#REVIEW#needs_review',
  GSI2SK: '2026-07-24#evt-1',
  eventId: 'evt-1',
  elderId: 'elder-1',
  eventType: 'meal',
  content: '早餐吃地瓜稀飯',
  originalUtterance: '我早餐吃了地瓜稀飯',
  eventDate: '2026-07-24',
  confidence: 0.8,
  sourceConversationId: 'conv-1',
  reviewStatus: 'needs_review',
  reviewHistory: [],
  createdAt: '2026-07-24T00:00:00Z',
  updatedAt: '2026-07-24T00:00:00Z',
  ttl: 0,
};

describe('listEventsHandler', () => {
  beforeEach(() => { ddbMock.reset(); });

  it('rejects a caregiver requesting an elder outside their assignment (H01.2, H01.3)', async () => {
    const res = await listEventsHandler(fakeEvent({ pathParameters: { elderId: 'elder-999' } }));
    expect(res.statusCode).toBe(403);
  });

  it('returns events for an authorized elder', async () => {
    ddbMock.on(QueryCommand).resolves({ Items: [existingEvent] });
    const res = await listEventsHandler(fakeEvent({ pathParameters: { elderId: 'elder-1' } }));
    expect(res.statusCode).toBe(200);
    const body = JSON.parse(res.body);
    expect(body.items).toHaveLength(1);
    expect(body.items[0].eventId).toBe('evt-1');
  });
});

describe('updateEventHandler', () => {
  beforeEach(() => { ddbMock.reset(); });

  it('records a before/after diff in reviewHistory and persists it (B03.2, Property-9-style append-only)', async () => {
    ddbMock.on(GetCommand).resolves({ Item: existingEvent });
    ddbMock.on(PutCommand).resolves({});

    const res = await updateEventHandler(
      fakeEvent({
        pathParameters: { eventId: 'evt-1' },
        body: JSON.stringify({
          elderId: 'elder-1',
          eventDate: '2026-07-24',
          content: '早餐吃地瓜稀飯和一顆蛋',
          reviewStatus: 'caregiver_confirmed',
          updatedBy: 'cg1',
        }),
      }),
    );

    expect(res.statusCode).toBe(200);
    const putCall = ddbMock.commandCalls(PutCommand)[0];
    const savedItem = putCall!.args[0].input.Item as EventRecord;
    expect(savedItem.content).toBe('早餐吃地瓜稀飯和一顆蛋');
    expect(savedItem.reviewStatus).toBe('caregiver_confirmed');
    expect(savedItem.reviewHistory).toHaveLength(2); // content change + reviewStatus change
    expect(savedItem.reviewHistory[0]).toMatchObject({ field: 'content', previousValue: '早餐吃地瓜稀飯', changedBy: 'cg1' });
  });

  it('returns 404 when the event does not exist', async () => {
    ddbMock.on(GetCommand).resolves({ Item: undefined });
    const res = await updateEventHandler(
      fakeEvent({
        pathParameters: { eventId: 'missing' },
        body: JSON.stringify({ elderId: 'elder-1', eventDate: '2026-07-24', updatedBy: 'cg1' }),
      }),
    );
    expect(res.statusCode).toBe(404);
  });
});
