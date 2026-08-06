import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import {
  DeleteCommand,
  DynamoDBDocumentClient,
  GetCommand,
  PutCommand,
  QueryCommand,
  ScanCommand,
  UpdateCommand,
  type QueryCommandInput,
} from '@aws-sdk/lib-dynamodb';

export interface TableConfig {
  tableName: string;
  gsi1Name: string;
  gsi2Name: string;
}

const DEFAULT_TABLE_CONFIG: TableConfig = {
  tableName: process.env.DYNAMODB_TABLE_NAME ?? 'elderly-care-main',
  gsi1Name: process.env.DYNAMODB_GSI1_NAME ?? 'GSI1',
  gsi2Name: process.env.DYNAMODB_GSI2_NAME ?? 'GSI2',
};

let cachedClient: DynamoDBDocumentClient | null = null;

function getDocumentClient(): DynamoDBDocumentClient {
  if (!cachedClient) {
    const raw = new DynamoDBClient({
      endpoint: process.env.DYNAMODB_ENDPOINT, // set for local dev / dynamodb-local
    });
    cachedClient = DynamoDBDocumentClient.from(raw, {
      marshallOptions: { removeUndefinedValues: true },
    });
  }
  return cachedClient;
}

/**
 * Thin repository wrapper around the DynamoDB single-table. Every read/write here
 * operates on a PK/SK item; elder-scoping is enforced by callers always deriving
 * PK from Keys.elderPk(elderId) (see db/keys.ts) rather than by this layer guessing intent.
 */
export class DynamoTable {
  constructor(
    private readonly config: TableConfig = DEFAULT_TABLE_CONFIG,
    private readonly client: DynamoDBDocumentClient = getDocumentClient(),
  ) {}

  async getItem<T>(pk: string, sk: string): Promise<T | null> {
    const result = await this.client.send(
      new GetCommand({ TableName: this.config.tableName, Key: { PK: pk, SK: sk } }),
    );
    return (result.Item as T | undefined) ?? null;
  }

  async putItem<T extends object>(item: T): Promise<void> {
    await this.client.send(new PutCommand({ TableName: this.config.tableName, Item: item }));
  }

  async deleteItem(pk: string, sk: string): Promise<void> {
    await this.client.send(
      new DeleteCommand({ TableName: this.config.tableName, Key: { PK: pk, SK: sk } }),
    );
  }

  /** Query all items under a partition, optionally with an SK begins_with prefix. */
  async queryByPk<T>(pk: string, skPrefix?: string, limit?: number): Promise<T[]> {
    const params: QueryCommandInput = {
      TableName: this.config.tableName,
      KeyConditionExpression: skPrefix
        ? 'PK = :pk AND begins_with(SK, :skPrefix)'
        : 'PK = :pk',
      ExpressionAttributeValues: skPrefix
        ? { ':pk': pk, ':skPrefix': skPrefix }
        : { ':pk': pk },
      Limit: limit,
    };
    const result = await this.client.send(new QueryCommand(params));
    return (result.Items as T[] | undefined) ?? [];
  }

  async queryGsi1<T>(gsi1pk: string, skPrefix?: string): Promise<T[]> {
    const result = await this.client.send(
      new QueryCommand({
        TableName: this.config.tableName,
        IndexName: this.config.gsi1Name,
        KeyConditionExpression: skPrefix
          ? 'GSI1PK = :pk AND begins_with(GSI1SK, :skPrefix)'
          : 'GSI1PK = :pk',
        ExpressionAttributeValues: skPrefix
          ? { ':pk': gsi1pk, ':skPrefix': skPrefix }
          : { ':pk': gsi1pk },
      }),
    );
    return (result.Items as T[] | undefined) ?? [];
  }

  async queryGsi2<T>(gsi2pk: string, skPrefix?: string): Promise<T[]> {
    const result = await this.client.send(
      new QueryCommand({
        TableName: this.config.tableName,
        IndexName: this.config.gsi2Name,
        KeyConditionExpression: skPrefix
          ? 'GSI2PK = :pk AND begins_with(GSI2SK, :skPrefix)'
          : 'GSI2PK = :pk',
        ExpressionAttributeValues: skPrefix
          ? { ':pk': gsi2pk, ':skPrefix': skPrefix }
          : { ':pk': gsi2pk },
      }),
    );
    return (result.Items as T[] | undefined) ?? [];
  }

  /**
   * Full-table scan filtered by a SK equality condition — used only for
   * small, infrequent batch jobs (e.g. "every elder profile" for the daily
   * summary trigger). At production scale this should become a GSI; a scan
   * is acceptable for a demo-sized tenant.
   */
  async scanBySk<T>(sk: string): Promise<T[]> {
    const items: T[] = [];
    let exclusiveStartKey: Record<string, unknown> | undefined;
    do {
      const result = await this.client.send(
        new ScanCommand({
          TableName: this.config.tableName,
          FilterExpression: 'SK = :sk',
          ExpressionAttributeValues: { ':sk': sk },
          ExclusiveStartKey: exclusiveStartKey,
        }),
      );
      items.push(...((result.Items as T[] | undefined) ?? []));
      exclusiveStartKey = result.LastEvaluatedKey;
    } while (exclusiveStartKey);
    return items;
  }

  async updateItem(
    pk: string,
    sk: string,
    updateExpression: string,
    expressionAttributeValues: Record<string, unknown>,
    expressionAttributeNames?: Record<string, string>,
  ): Promise<void> {
    await this.client.send(
      new UpdateCommand({
        TableName: this.config.tableName,
        Key: { PK: pk, SK: sk },
        UpdateExpression: updateExpression,
        ExpressionAttributeValues: expressionAttributeValues,
        ExpressionAttributeNames: expressionAttributeNames,
      }),
    );
  }
}

export function createDynamoTable(config?: Partial<TableConfig>): DynamoTable {
  return new DynamoTable({ ...DEFAULT_TABLE_CONFIG, ...config });
}
