import type { NotificationPreferences } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';

/**
 * Reads/writes a family member's NotificationPreferences record, including
 * the unsubscribe path (C03.4) — setting `subscribed: false` is what
 * NotificationService checks before dispatching anything.
 */
export class NotificationPreferencesStore {
  constructor(private readonly table: DynamoTable = new DynamoTable()) {}

  async get(familyId: string): Promise<NotificationPreferences | null> {
    return this.table.getItem<NotificationPreferences>(Keys.familyPk(familyId), Keys.notificationPrefSk());
  }

  async update(familyId: string, updates: Partial<Omit<NotificationPreferences, 'PK' | 'SK' | 'familyId'>>): Promise<NotificationPreferences> {
    const existing = await this.get(familyId);
    const merged: NotificationPreferences = {
      PK: Keys.familyPk(familyId),
      SK: 'NOTIF_PREF',
      familyId,
      frequency: existing?.frequency ?? 'daily',
      channels: existing?.channels ?? ['email'],
      quietHoursStart: existing?.quietHoursStart ?? '22:00',
      quietHoursEnd: existing?.quietHoursEnd ?? '07:00',
      enabledCategories: existing?.enabledCategories ?? [],
      subscribed: existing?.subscribed ?? true,
      ...updates,
    };
    await this.table.putItem(merged);
    return merged;
  }

  async unsubscribe(familyId: string): Promise<void> {
    await this.update(familyId, { subscribed: false });
  }
}
