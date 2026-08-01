import { DeleteObjectCommand, S3Client } from '@aws-sdk/client-s3';
import { unmarshall } from '@aws-sdk/util-dynamodb';
import type { DynamoDBStreamEvent, DynamoDBRecord } from 'aws-lambda';
import { Client as OpenSearchClient } from '@opensearch-project/opensearch';
import { getOpenSearchClient } from '../search/index-management.js';
import { MEMORY_VECTORS_INDEX_NAME } from '../search/index-mappings.js';

/** Marks a DynamoDB Streams REMOVE event as TTL-driven rather than an explicit delete-item call. */
function isTtlExpiry(record: DynamoDBRecord): boolean {
  return record.eventName === 'REMOVE' && record.userIdentity?.principalId === 'dynamodb.amazonaws.com';
}

export interface TtlCleanupDeps {
  s3: S3Client;
  openSearch: OpenSearchClient;
  audioBucket: string;
}

/**
 * Cross-store TTL cleanup (H03.3, Property 12's sibling for *automatic*
 * deletion): when DynamoDB expires an item via TTL, this stream handler
 * removes whatever that item had fanned out to elsewhere — the S3 audio
 * object for an expired conversation, or the OpenSearch vector for an
 * expired memory. Explicit user-initiated deletes (MemoryManager.delete)
 * already handle their own cross-store cleanup directly; this handler only
 * covers the *automatic* expiry path, which is why it filters to
 * dynamodb.amazonaws.com-initiated removals.
 */
export async function cleanupExpiredItem(record: DynamoDBRecord, deps: TtlCleanupDeps): Promise<void> {
  if (!isTtlExpiry(record) || !record.dynamodb?.OldImage) return;

  const item = unmarshall(record.dynamodb.OldImage as Record<string, never>) as Record<string, unknown>;
  const sk = String(item.SK ?? '');

  if (sk.startsWith('CONV#') && typeof item.audioS3Key === 'string' && item.audioS3Key) {
    await deps.s3.send(new DeleteObjectCommand({ Bucket: deps.audioBucket, Key: item.audioS3Key }));
  } else if (sk.startsWith('MEM#') || sk.startsWith('CMEM#')) {
    const memoryId = String(item.memoryId ?? '');
    if (memoryId) {
      await deps.openSearch.delete({ index: MEMORY_VECTORS_INDEX_NAME, id: memoryId }).catch((err) => {
        // A memory that was never indexed (e.g. rejected candidates) has
        // nothing to delete — 404 from OpenSearch is expected, not an error.
        if (!(err instanceof Error) || !err.message.includes('404')) throw err;
      });
    }
  }
}

export async function handler(event: DynamoDBStreamEvent): Promise<void> {
  const deps: TtlCleanupDeps = {
    s3: new S3Client({}),
    openSearch: getOpenSearchClient(),
    audioBucket: process.env.AUDIO_BUCKET_NAME ?? '',
  };

  for (const record of event.Records) {
    try {
      await cleanupExpiredItem(record, deps);
    } catch (err) {
      console.error('[retention] failed to clean up expired item', err instanceof Error ? err.message : err);
    }
  }
}
