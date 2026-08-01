import { PublishCommand, SNSClient } from '@aws-sdk/client-sns';
import { SendEmailCommand, SESClient } from '@aws-sdk/client-ses';
import type { NotificationChannel } from '@elderly-care/shared';
import { isWithinQuietHours } from './quiet-hours.js';
import type { AlertPayload, AnomalyInfo, DailySummaryPayload, NotificationTarget } from './types.js';

/**
 * NotificationService (C03) — dispatches across whatever channels a target
 * has configured. Two rules govern whether a message goes out at all:
 *  - subscribed === false always suppresses everything (unsubscribe, C03.4)
 *  - quiet hours suppress *summaries* but never alerts — a high-risk alert
 *    is immediate by definition (C03.3) and must reach Family regardless of
 *    the hour.
 */
export class NotificationService {
  constructor(
    private readonly sns: SNSClient = new SNSClient({}),
    private readonly ses: SESClient = new SESClient({}),
  ) {}

  async sendSummary(target: NotificationTarget, summary: DailySummaryPayload, now: Date = new Date()): Promise<void> {
    if (!target.preferences.subscribed) return;
    if (isWithinQuietHours(now, target.preferences.quietHoursStart, target.preferences.quietHoursEnd)) return;
    await this.dispatch(target, `${summary.elderName} 的每日摘要（${summary.date}）`, summary.overview);
  }

  /** Bypasses quiet hours and frequency preferences — high-risk alerts are always immediate. */
  async sendAlert(target: NotificationTarget, alert: AlertPayload): Promise<void> {
    if (!target.preferences.subscribed) return;
    await this.dispatch(target, alert.title, alert.message);
  }

  async sendAnomalyNotification(target: NotificationTarget, anomaly: AnomalyInfo): Promise<void> {
    if (!target.preferences.subscribed) return;
    await this.dispatch(
      target,
      `${anomaly.elderName} 連續互動異常`,
      `${anomaly.elderName} 已連續 ${anomaly.consecutiveFailures} 次語音互動失敗，最後嘗試時間：${anomaly.lastAttemptAt}`,
    );
  }

  private async dispatch(target: NotificationTarget, subject: string, body: string): Promise<void> {
    await Promise.all(target.channels.map((channel) => this.sendViaChannel(channel, target, subject, body)));
  }

  private async sendViaChannel(
    channel: NotificationChannel,
    target: NotificationTarget,
    subject: string,
    body: string,
  ): Promise<void> {
    const address = target.addresses[channel];
    if (!address) return;

    switch (channel) {
      case 'email':
        await this.ses.send(
          new SendEmailCommand({
            Source: process.env.NOTIFICATION_FROM_EMAIL ?? 'noreply@elderly-care.example',
            Destination: { ToAddresses: [address] },
            Message: { Subject: { Data: subject }, Body: { Text: { Data: body } } },
          }),
        );
        return;
      case 'sms':
        await this.sns.send(new PublishCommand({ PhoneNumber: address, Message: `${subject}\n${body}` }));
        return;
      case 'push':
        await this.sns.send(
          new PublishCommand({ TargetArn: address, Message: JSON.stringify({ default: `${subject}: ${body}` }) }),
        );
        return;
      case 'line':
        // LINE Notify integration is out of scope for the MVP; logged so
        // the gap is visible in ops rather than silently dropped.
        console.warn('[notification] LINE channel not yet implemented, skipping', { userId: target.userId });
        return;
    }
  }
}
