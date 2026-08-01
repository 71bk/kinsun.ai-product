import type { NotificationChannel, NotificationFrequency } from '@elderly-care/shared';

export interface NotificationPreferencesConfig {
  frequency: NotificationFrequency;
  quietHoursStart: string; // "22:00"
  quietHoursEnd: string; // "07:00"
  enabledCategories: string[];
  subscribed: boolean;
}

export interface NotificationTarget {
  userId: string;
  role: 'caregiver' | 'family';
  channels: NotificationChannel[];
  preferences: NotificationPreferencesConfig;
  /** Destination addresses keyed by channel — e.g. { email: 'x@y.com', sms: '+886...' }. */
  addresses: Partial<Record<NotificationChannel, string>>;
}

export interface DailySummaryPayload {
  elderName: string;
  date: string;
  overview: string;
}

export interface AlertPayload {
  severity: 'critical' | 'high' | 'medium';
  title: string;
  message: string;
  category: string;
}

export interface AnomalyInfo {
  elderName: string;
  consecutiveFailures: number;
  lastAttemptAt: string;
}
