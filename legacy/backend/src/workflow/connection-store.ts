import { DynamoTable, Keys } from '../db/index.js';

export interface ConnectionRecord {
  PK: string;
  SK: string;
  connectionId: string;
  elderId: string;
  role: string;
  connectedAt: string;
  conversationId: string | null;
  traceId: string | null;
  ttl: number;
}

const CONNECTION_TTL_SECONDS = 60 * 60 * 4; // 4h — a voice session shouldn't outlive this

export class ConnectionStore {
  constructor(private readonly table: DynamoTable = new DynamoTable()) {}

  async save(connectionId: string, elderId: string, role: string): Promise<void> {
    const record: ConnectionRecord = {
      PK: Keys.connectionPk(connectionId),
      SK: Keys.connectionSk(),
      connectionId,
      elderId,
      role,
      connectedAt: new Date().toISOString(),
      conversationId: null,
      traceId: null,
      ttl: Math.floor(Date.now() / 1000) + CONNECTION_TTL_SECONDS,
    };
    await this.table.putItem(record);
  }

  async get(connectionId: string): Promise<ConnectionRecord | null> {
    return this.table.getItem<ConnectionRecord>(Keys.connectionPk(connectionId), Keys.connectionSk());
  }

  async attachConversation(connectionId: string, conversationId: string, traceId: string): Promise<void> {
    await this.table.updateItem(
      Keys.connectionPk(connectionId),
      Keys.connectionSk(),
      'SET conversationId = :cid, traceId = :tid',
      { ':cid': conversationId, ':tid': traceId },
    );
  }

  async remove(connectionId: string): Promise<void> {
    await this.table.deleteItem(Keys.connectionPk(connectionId), Keys.connectionSk());
  }
}
