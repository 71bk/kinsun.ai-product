/**
 * Language codes supported by ASR/TTS/Persona.
 * zh-TW = Mandarin, nan-TW = Taiwanese Hokkien, hak-TW = Hakka, en-US = English.
 */
export type Language = 'zh-TW' | 'nan-TW' | 'hak-TW' | 'en-US' | 'mixed';

export type RecordingState = 'idle' | 'recording' | 'processing' | 'playing';

export type EventType =
  | 'meal'
  | 'activity'
  | 'sleep'
  | 'medication_statement'
  | 'emotion'
  | 'important_event';

export type ReviewStatus =
  | 'auto_approved'
  | 'needs_review'
  | 'caregiver_confirmed'
  | 'caregiver_rejected';

export type MemoryCategory =
  | 'preference'
  | 'relationship'
  | 'routine'
  | 'health_condition'
  | 'life_event';

export type MemoryStatus = 'pending' | 'confirmed' | 'rejected' | 'deleted';

export type SummaryStatus = 'draft' | 'published' | 'withdrawn';

export type UserRole = 'elder' | 'caregiver' | 'family' | 'admin';

export type NotificationChannel = 'push' | 'email' | 'sms' | 'line';

export type NotificationFrequency = 'daily' | 'weekly' | 'realtime';

export type ConsentStatus = 'not_consented' | 'pending' | 'consented' | 'revoked';

export type GuardrailAction = 'pass' | 'block' | 'redact';

export type ReportRange = 'week' | 'year';
