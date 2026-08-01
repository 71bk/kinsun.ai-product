import { marshall } from '@aws-sdk/util-dynamodb';
import { describe, expect, it, vi } from 'vitest';
import type { DynamoDBRecord } from 'aws-lambda';
import { cleanupExpiredItem, type TtlCleanupDeps } from './ttl-stream-handler.js';

function ttlRemoveRecord(oldImage: Record<string, unknown>): DynamoDBRecord {
  return {
    eventName: 'REMOVE',
    userIdentity: { type: 'Service', principalId: 'dynamodb.amazonaws.com' },
    dynamodb: { OldImage: marshall(oldImage) as never },
  } as DynamoDBRecord;
}

function explicitRemoveRecord(oldImage: Record<string, unknown>): DynamoDBRecord {
  return {
    eventName: 'REMOVE',
    dynamodb: { OldImage: marshall(oldImage) as never },
  } as DynamoDBRecord;
}

function fakeDeps(): TtlCleanupDeps & { s3Calls: unknown[]; osCalls: unknown[] } {
  const s3Calls: unknown[] = [];
  const osCalls: unknown[] = [];
  return {
    s3: { send: vi.fn((cmd) => { s3Calls.push(cmd); return Promise.resolve({}); }) } as never,
    openSearch: { delete: vi.fn((params) => { osCalls.push(params); return Promise.resolve({}); }) } as never,
    audioBucket: 'test-audio-bucket',
    s3Calls,
    osCalls,
  };
}

describe('cleanupExpiredItem (H03.3)', () => {
  it('deletes the S3 audio object when a TTL-expired conversation had one', async () => {
    const deps = fakeDeps();
    await cleanupExpiredItem(
      ttlRemoveRecord({ PK: 'ELDER#e1', SK: 'CONV#2026-01-01#c1', audioS3Key: 'audio/e1/c1.opus' }),
      deps,
    );
    expect(deps.s3Calls).toHaveLength(1);
  });

  it('does nothing for a TTL-expired conversation with no audio', async () => {
    const deps = fakeDeps();
    await cleanupExpiredItem(ttlRemoveRecord({ PK: 'ELDER#e1', SK: 'CONV#2026-01-01#c1', audioS3Key: null }), deps);
    expect(deps.s3Calls).toHaveLength(0);
  });

  it('removes the OpenSearch vector for a TTL-expired memory', async () => {
    const deps = fakeDeps();
    await cleanupExpiredItem(ttlRemoveRecord({ PK: 'ELDER#e1', SK: 'CMEM#m1', memoryId: 'm1' }), deps);
    expect(deps.osCalls).toHaveLength(1);
  });

  it('ignores an explicit (non-TTL) delete — that path already handles its own cross-store cleanup', async () => {
    const deps = fakeDeps();
    await cleanupExpiredItem(explicitRemoveRecord({ PK: 'ELDER#e1', SK: 'MEM#m1', memoryId: 'm1' }), deps);
    expect(deps.s3Calls).toHaveLength(0);
    expect(deps.osCalls).toHaveLength(0);
  });
});
