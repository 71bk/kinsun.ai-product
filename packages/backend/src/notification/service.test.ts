import { PublishCommand, SNSClient } from '@aws-sdk/client-sns';
import { SendEmailCommand, SESClient } from '@aws-sdk/client-ses';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it } from 'vitest';
import { FAILURE_NOTIFICATION_THRESHOLD, FailureTracker, type FailureCountStore } from './failure-tracker.js';
import { NotificationService } from './service.js';
import { isWithinQuietHours } from './quiet-hours.js';
import type { NotificationTarget } from './types.js';

const snsMock = mockClient(SNSClient);
const sesMock = mockClient(SESClient);

const target: NotificationTarget = {
  userId: 'fm-1',
  role: 'family',
  channels: ['email'],
  preferences: {
    frequency: 'daily',
    quietHoursStart: '22:00',
    quietHoursEnd: '07:00',
    enabledCategories: ['summary'],
    subscribed: true,
  },
  addresses: { email: 'family@example.com' },
};

describe('isWithinQuietHours', () => {
  it('detects an overnight window correctly', () => {
    expect(isWithinQuietHours(new Date('2026-07-24T23:00:00'), '22:00', '07:00')).toBe(true);
    expect(isWithinQuietHours(new Date('2026-07-24T03:00:00'), '22:00', '07:00')).toBe(true);
    expect(isWithinQuietHours(new Date('2026-07-24T12:00:00'), '22:00', '07:00')).toBe(false);
  });

  it('detects a same-day window correctly', () => {
    expect(isWithinQuietHours(new Date('2026-07-24T13:00:00'), '12:00', '14:00')).toBe(true);
    expect(isWithinQuietHours(new Date('2026-07-24T15:00:00'), '12:00', '14:00')).toBe(false);
  });
});

describe('NotificationService', () => {
  beforeEach(() => {
    snsMock.reset();
    sesMock.reset();
  });

  it('does not send a summary during quiet hours', async () => {
    sesMock.on(SendEmailCommand).resolves({});
    const service = new NotificationService(new SNSClient({}), new SESClient({}));
    await service.sendSummary(
      target,
      { elderName: '林阿嬤', date: '2026-07-24', overview: '今日狀況良好' },
      new Date('2026-07-24T23:30:00'),
    );
    expect(sesMock.calls()).toHaveLength(0);
  });

  it('sends a summary outside quiet hours', async () => {
    sesMock.on(SendEmailCommand).resolves({});
    const service = new NotificationService(new SNSClient({}), new SESClient({}));
    await service.sendSummary(
      target,
      { elderName: '林阿嬤', date: '2026-07-24', overview: '今日狀況良好' },
      new Date('2026-07-24T10:00:00'),
    );
    expect(sesMock.calls()).toHaveLength(1);
  });

  it('sends a high-risk alert immediately, even during quiet hours', async () => {
    sesMock.on(SendEmailCommand).resolves({});
    const service = new NotificationService(new SNSClient({}), new SESClient({}));
    await service.sendAlert(target, { severity: 'critical', title: '緊急狀況', message: '長者回報胸痛', category: 'emergency' });
    expect(sesMock.calls()).toHaveLength(1);
  });

  it('never sends anything to an unsubscribed target', async () => {
    sesMock.on(SendEmailCommand).resolves({});
    const unsubscribed: NotificationTarget = { ...target, preferences: { ...target.preferences, subscribed: false } };
    const service = new NotificationService(new SNSClient({}), new SESClient({}));
    await service.sendAlert(unsubscribed, { severity: 'critical', title: 'x', message: 'y', category: 'z' });
    await service.sendSummary(unsubscribed, { elderName: '林阿嬤', date: '2026-07-24', overview: 'x' }, new Date('2026-07-24T10:00:00'));
    expect(sesMock.calls()).toHaveLength(0);
  });
});

class InMemoryFailureStore implements FailureCountStore {
  private items = new Map<string, unknown>();
  async getItem<T>(pk: string, sk: string): Promise<T | null> {
    return (this.items.get(`${pk}::${sk}`) as T | undefined) ?? null;
  }
  async putItem<T extends object>(item: T): Promise<void> {
    const { PK, SK } = item as unknown as { PK: string; SK: string };
    this.items.set(`${PK}::${SK}`, item);
  }
}

describe('FailureTracker', () => {
  it('resets the streak to 0 on a success', async () => {
    const tracker = new FailureTracker(new InMemoryFailureStore());
    await tracker.recordInteractionResult('e1', false);
    await tracker.recordInteractionResult('e1', false);
    await tracker.recordInteractionResult('e1', true);
    expect(await tracker.getConsecutiveFailureCount('e1')).toBe(0);
  });

  it('triggers shouldNotify exactly on the 3rd consecutive failure, not before or after', async () => {
    const tracker = new FailureTracker(new InMemoryFailureStore());
    const r1 = await tracker.recordInteractionResult('e1', false);
    const r2 = await tracker.recordInteractionResult('e1', false);
    const r3 = await tracker.recordInteractionResult('e1', false);
    const r4 = await tracker.recordInteractionResult('e1', false);

    expect(r1.shouldNotify).toBe(false);
    expect(r2.shouldNotify).toBe(false);
    expect(r3.count).toBe(FAILURE_NOTIFICATION_THRESHOLD);
    expect(r3.shouldNotify).toBe(true);
    expect(r4.shouldNotify).toBe(false); // already notified at 3; don't spam on 4, 5, ...
  });
});
