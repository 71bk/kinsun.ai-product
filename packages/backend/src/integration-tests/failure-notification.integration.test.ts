import { SNSClient } from '@aws-sdk/client-sns';
import { SendEmailCommand, SESClient } from '@aws-sdk/client-ses';
import { mockClient } from 'aws-sdk-client-mock';
import { beforeEach, describe, expect, it } from 'vitest';
import { FailureTracker, type FailureCountStore } from '../notification/failure-tracker.js';
import { NotificationService } from '../notification/service.js';
import type { NotificationTarget } from '../notification/types.js';

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

const sesMock = mockClient(SESClient);

const familyTarget: NotificationTarget = {
  userId: 'fm-1',
  role: 'family',
  channels: ['email'],
  preferences: {
    frequency: 'realtime',
    quietHoursStart: '22:00',
    quietHoursEnd: '07:00',
    enabledCategories: ['alert'],
    subscribed: true,
  },
  addresses: { email: 'family@example.invalid' },
};

/**
 * 連續失敗通知整合測試 (task 25.3, A01.5). Runs FailureTracker across a
 * realistic sequence of interaction outcomes and, at the exact call where
 * it reports shouldNotify, feeds that straight into the real
 * NotificationService.sendAnomalyNotification — checking the two modules
 * agree on when a notification should fire, not just that each does its
 * own job in isolation.
 */
describe('Integration: consecutive ASR failures -> anomaly notification', () => {
  beforeEach(() => { sesMock.reset(); });

  it('notifies exactly once, on the 3rd consecutive failure, during a mixed success/failure sequence', async () => {
    const tracker = new FailureTracker(new InMemoryFailureStore());
    const notificationService = new NotificationService(new SNSClient({}), new SESClient({}));
    sesMock.on(SendEmailCommand).resolves({});

    const outcomes = [true, false, false, false, false]; // success, then 4 consecutive failures
    let notificationsSent = 0;

    for (const success of outcomes) {
      const result = await tracker.recordInteractionResult('elder-1', success);
      if (result.shouldNotify) {
        await notificationService.sendAnomalyNotification(familyTarget, {
          elderName: '林阿嬤',
          consecutiveFailures: result.count,
          lastAttemptAt: '2026-07-24T09:00:00Z',
        });
        notificationsSent++;
      }
    }

    expect(notificationsSent).toBe(1); // only the 3rd consecutive failure, not the 4th
    expect(sesMock.calls()).toHaveLength(1);
    const emailArgs = sesMock.commandCalls(SendEmailCommand)[0]!.args[0].input;
    expect(JSON.stringify(emailArgs)).toContain('林阿嬤');
  });

  it('never notifies an unsubscribed family member even when the failure threshold is reached', async () => {
    const tracker = new FailureTracker(new InMemoryFailureStore());
    const notificationService = new NotificationService(new SNSClient({}), new SESClient({}));
    sesMock.on(SendEmailCommand).resolves({});
    const unsubscribed: NotificationTarget = { ...familyTarget, preferences: { ...familyTarget.preferences, subscribed: false } };

    for (let i = 0; i < 3; i++) {
      const result = await tracker.recordInteractionResult('elder-1', false);
      if (result.shouldNotify) {
        await notificationService.sendAnomalyNotification(unsubscribed, {
          elderName: '林阿嬤',
          consecutiveFailures: result.count,
          lastAttemptAt: '2026-07-24T09:00:00Z',
        });
      }
    }

    expect(sesMock.calls()).toHaveLength(0);
  });
});
