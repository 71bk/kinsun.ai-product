import type { MemoryDataStore } from './manager.js';

/** In-memory MemoryDataStore fake for property tests — no AWS mocking needed. */
export class InMemoryStore implements MemoryDataStore {
  private items = new Map<string, unknown>();

  private key(pk: string, sk: string): string {
    return `${pk}::${sk}`;
  }

  async getItem<T>(pk: string, sk: string): Promise<T | null> {
    return (this.items.get(this.key(pk, sk)) as T | undefined) ?? null;
  }

  async putItem<T extends object>(item: T): Promise<void> {
    const { PK, SK } = item as unknown as { PK: string; SK: string };
    this.items.set(this.key(PK, SK), item);
  }

  async deleteItem(pk: string, sk: string): Promise<void> {
    this.items.delete(this.key(pk, sk));
  }

  async queryByPk<T>(pk: string, skPrefix?: string): Promise<T[]> {
    const results: T[] = [];
    for (const [key, value] of this.items.entries()) {
      const [itemPk, itemSk] = key.split('::');
      if (itemPk !== pk) continue;
      if (skPrefix && !itemSk!.startsWith(skPrefix)) continue;
      results.push(value as T);
    }
    return results;
  }

  has(pk: string, sk: string): boolean {
    return this.items.has(this.key(pk, sk));
  }
}
