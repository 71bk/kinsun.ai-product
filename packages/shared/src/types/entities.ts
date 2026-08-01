import type {
  ConsentStatus,
  EventType,
  Language,
  MemoryCategory,
  MemoryStatus,
  ReviewStatus,
  SummaryStatus,
} from './enums.js';

/** DynamoDB single-table item base — every entity carries PK/SK. See design.md §資料模型. */
export interface DynamoItem {
  PK: string;
  SK: string;
}

// ---------------------------------------------------------------------------
// Elder / Persona
// ---------------------------------------------------------------------------

export interface ElderProfile extends DynamoItem {
  SK: 'PROFILE';
  elderId: string;
  tenantId: string;
  name: string;
  dateOfBirth: string;
  primaryLanguage: Language;
  secondaryLanguages: Language[];
  consentStatus: ConsentStatus;
  createdAt: string;
  updatedAt: string;
}

export interface PersonaRecord extends DynamoItem {
  SK: 'PERSONA';
  elderId: string;
  displayName: string;
  preferredLanguage: Language;
  responseLength: 'short' | 'medium' | 'long';
  speakingSpeed: 'slow' | 'normal' | 'fast';
  interactionStyle: 'formal' | 'casual' | 'warm';
  customGreeting: string;
  updatedAt: string;
  updatedBy: string;
}

export interface PersonaContext {
  displayName: string;
  preferredLanguage: Language;
  responseLength: 'short' | 'medium' | 'long';
  speakingSpeed: 'slow' | 'normal' | 'fast';
  interactionStyle: 'formal' | 'casual' | 'warm';
  customGreeting: string;
}

// ---------------------------------------------------------------------------
// Conversation
// ---------------------------------------------------------------------------

export interface ConversationTurn {
  role: 'elder' | 'assistant';
  content: string;
  timestamp: string;
  language: Language;
  confidence?: number;
}

export interface ASRMetadata {
  serviceEndpoint: string;
  modelVersion: string;
  latencyMs: number;
  language: Language;
}

export interface ConversationRecord extends DynamoItem {
  conversationId: string;
  elderId: string;
  startTime: string;
  endTime: string | null;
  turns: ConversationTurn[];
  asrMetadata: ASRMetadata | null;
  status: 'active' | 'completed' | 'failed';
  traceId: string;
  audioS3Key: string | null;
  ttl: number;
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

export interface ReviewChange {
  previousValue: string;
  newValue: string;
  changedBy: string;
  changedAt: string;
  field: string;
}

export interface EventRecord extends DynamoItem {
  GSI1PK: string; // ELDER#{elderId}#EVENT_TYPE#{type}
  GSI1SK: string; // {date}
  GSI2PK: string; // ELDER#{elderId}#REVIEW#{status}
  GSI2SK: string; // {date}#{eventId}
  eventId: string;
  elderId: string;
  eventType: EventType;
  content: string;
  originalUtterance: string;
  eventDate: string;
  confidence: number;
  sourceConversationId: string;
  reviewStatus: ReviewStatus;
  reviewHistory: ReviewChange[];
  createdAt: string;
  updatedAt: string;
  ttl: number;
}

/** Extracted-but-not-yet-persisted event, output of the Event Extractor before it is validated. */
export interface ExtractedEvent {
  eventId: string;
  elderId: string;
  eventType: EventType;
  content: string;
  originalUtterance: string;
  eventDate: string;
  confidence: number;
  sourceConversationId: string;
  reviewStatus: ReviewStatus;
  createdAt: string;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Memory (candidate / confirmed)
// ---------------------------------------------------------------------------

export interface AuditEntry {
  action: 'created' | 'confirmed' | 'rejected' | 'updated' | 'deactivated' | 'deleted';
  performedBy: string;
  performedAt: string;
  details: string;
}

export interface MemoryRecord extends DynamoItem {
  memoryId: string;
  elderId: string;
  category: MemoryCategory;
  content: string;
  sourceConversationId: string;
  confidence: number;
  status: MemoryStatus;
  confirmedBy: string | null;
  confirmedAt: string | null;
  isActive: boolean;
  lastUsedAt: string | null;
  createdAt: string;
  updatedAt: string;
  auditTrail: AuditEntry[];
  ttl: number | null;
}

export interface CandidateMemory {
  memoryId: string;
  elderId: string;
  category: MemoryCategory;
  content: string;
  sourceConversationId: string;
  confidence: number;
  createdAt: string;
  status: 'pending' | 'confirmed' | 'rejected';
}

export interface ConfirmedMemory {
  memoryId: string;
  elderId: string;
  category: MemoryCategory;
  content: string;
  confirmedBy: string;
  confirmedAt: string;
  sourceConversationId: string;
  isActive: boolean;
  lastUsedAt: string | null;
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

export interface SummaryContent {
  overview: string;
  meals: string[];
  activities: string[];
  sleep: string | null;
  medicationStatements: string[];
  importantEvents: string[];
  emotionalState: string | null;
}

export interface SummaryRecord extends DynamoItem {
  summaryId: string;
  elderId: string;
  date: string;
  content: SummaryContent;
  sourceEventIds: string[];
  generatedAt: string;
  version: number;
  ttl: number;
  /** Family-facing visibility gate — family role only ever reads 'published'. See api/summaries.ts. */
  status: SummaryStatus;
  publishedAt: string | null;
  publishedBy: string | null;
}

// ---------------------------------------------------------------------------
// Consent
// ---------------------------------------------------------------------------

export interface ConsentRecord extends DynamoItem {
  elderId: string;
  type: 'recording' | 'data_processing';
  status: ConsentStatus;
  grantedAt: string | null;
  revokedAt: string | null;
  updatedAt: string;
}

// ---------------------------------------------------------------------------
// Caregiver / Family
// ---------------------------------------------------------------------------

export interface CaregiverProfile extends DynamoItem {
  SK: 'PROFILE';
  caregiverId: string;
  tenantId: string;
  name: string;
  email: string;
  createdAt: string;
}

export interface CaregiverElderMapping extends DynamoItem {
  caregiverId: string;
  elderId: string;
  assignedAt: string;
}

export interface FamilyMemberProfile extends DynamoItem {
  SK: 'PROFILE';
  familyId: string;
  name: string;
  email: string;
  createdAt: string;
}

export interface FamilyElderMapping extends DynamoItem {
  familyId: string;
  elderId: string;
  relationship: string;
}

export interface NotificationPreferences extends DynamoItem {
  SK: 'NOTIF_PREF';
  familyId: string;
  frequency: 'daily' | 'weekly' | 'realtime';
  channels: ('push' | 'email' | 'sms' | 'line')[];
  quietHoursStart: string; // "22:00"
  quietHoursEnd: string; // "07:00"
  enabledCategories: string[];
  subscribed: boolean;
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export interface AuditLogRecord extends DynamoItem {
  elderId: string;
  action: string;
  performedBy: string;
  performedAt: string;
  details: string;
  ttl: number;
}
