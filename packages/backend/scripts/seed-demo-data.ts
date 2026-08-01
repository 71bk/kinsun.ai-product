/**
 * Seeds fully fictional demo data for the "林阿嬤" (Lin Ah-ma) demo persona
 * described in requirements.md's Demo 必演流程. Run against a deployed
 * table via:
 *
 *   DYNAMODB_TABLE_NAME=elderly-care-main-dev npx tsx scripts/seed-demo-data.ts
 *
 * See README.md in this directory for the de-identification approach
 * (H05.1-H05.3) — every name, relationship, and utterance below is
 * invented for this demo and does not describe a real person.
 */
import { computeTtlEpochSeconds, DynamoTable, GSI1, GSI2, Keys, RETENTION_DAYS } from '../src/db/index.js';
import type {
  AuditEntry,
  CaregiverElderMapping,
  CaregiverProfile,
  ConsentRecord,
  ConversationRecord,
  ElderProfile,
  EventRecord,
  FamilyElderMapping,
  FamilyMemberProfile,
  MemoryRecord,
  NotificationPreferences,
  PersonaRecord,
  SummaryRecord,
} from '@elderly-care/shared';

const ELDER_ID = 'demo-elder-lin';
const CAREGIVER_ID = 'demo-caregiver-chen';
const FAMILY_ID = 'demo-family-lin-son';
const CONVERSATION_ID = 'demo-conv-001';
const TENANT_ID = 'demo-tenant';
const TODAY = new Date().toISOString().slice(0, 10);
const NOW = new Date().toISOString();

function auditEntry(action: AuditEntry['action'], performedBy: string, details: string): AuditEntry {
  return { action, performedBy, performedAt: NOW, details };
}

async function seed() {
  const table = new DynamoTable();

  const elder: ElderProfile = {
    PK: Keys.elderPk(ELDER_ID),
    SK: 'PROFILE',
    elderId: ELDER_ID,
    tenantId: TENANT_ID,
    name: '林阿嬤（示範角色）',
    dateOfBirth: '1945-03-12',
    primaryLanguage: 'nan-TW',
    secondaryLanguages: ['zh-TW'],
    consentStatus: 'consented',
    createdAt: NOW,
    updatedAt: NOW,
  };

  const persona: PersonaRecord = {
    PK: Keys.elderPk(ELDER_ID),
    SK: 'PERSONA',
    elderId: ELDER_ID,
    displayName: '林阿嬤',
    preferredLanguage: 'nan-TW',
    responseLength: 'short',
    speakingSpeed: 'slow',
    interactionStyle: 'warm',
    customGreeting: '阿嬤好，我在這裡陪你聊天喔！',
    updatedAt: NOW,
    updatedBy: 'system-seed',
  };

  const consent: ConsentRecord = {
    PK: Keys.elderPk(ELDER_ID),
    SK: Keys.consentSk('recording'),
    elderId: ELDER_ID,
    type: 'recording',
    status: 'consented',
    grantedAt: NOW,
    revokedAt: null,
    updatedAt: NOW,
  };

  const caregiver: CaregiverProfile = {
    PK: Keys.caregiverPk(CAREGIVER_ID),
    SK: 'PROFILE',
    caregiverId: CAREGIVER_ID,
    tenantId: TENANT_ID,
    name: '陳照服員（示範角色）',
    email: 'demo-caregiver@example.invalid',
    createdAt: NOW,
  };

  const caregiverMapping: CaregiverElderMapping = {
    PK: Keys.caregiverPk(CAREGIVER_ID),
    SK: Keys.caregiverElderMappingSk(ELDER_ID),
    caregiverId: CAREGIVER_ID,
    elderId: ELDER_ID,
    assignedAt: NOW,
  };

  const family: FamilyMemberProfile = {
    PK: Keys.familyPk(FAMILY_ID),
    SK: 'PROFILE',
    familyId: FAMILY_ID,
    name: '林小明（示範角色，林阿嬤之子）',
    email: 'demo-family@example.invalid',
    createdAt: NOW,
  };

  const familyMapping: FamilyElderMapping = {
    PK: Keys.familyPk(FAMILY_ID),
    SK: Keys.familyElderMappingSk(ELDER_ID),
    familyId: FAMILY_ID,
    elderId: ELDER_ID,
    relationship: '兒子',
  };

  const notificationPrefs: NotificationPreferences = {
    PK: Keys.familyPk(FAMILY_ID),
    SK: 'NOTIF_PREF',
    familyId: FAMILY_ID,
    frequency: 'daily',
    channels: ['email'],
    quietHoursStart: '22:00',
    quietHoursEnd: '07:00',
    enabledCategories: ['summary', 'alert'],
    subscribed: true,
  };

  // A short fictional Hokkien-language exchange matching the demo script's
  // "林阿嬤臺語對話" beat — invented for this demo, not a real transcript.
  const conversation: ConversationRecord = {
    PK: Keys.elderPk(ELDER_ID),
    SK: Keys.conversationSk(NOW, CONVERSATION_ID),
    conversationId: CONVERSATION_ID,
    elderId: ELDER_ID,
    startTime: NOW,
    endTime: NOW,
    turns: [
      { role: 'elder', content: '我今仔日中晝食糜佮菜脯，food了誠好食。', timestamp: NOW, language: 'nan-TW', confidence: 0.86 },
      { role: 'assistant', content: '阿嬤食甲真好喔！有出去散步無？', timestamp: NOW, language: 'nan-TW' },
      { role: 'elder', content: '有啦，透早有去公園行一下仔，行半點鐘。', timestamp: NOW, language: 'nan-TW', confidence: 0.81 },
      { role: 'elder', content: '我早起有食血壓的藥仔矣。', timestamp: NOW, language: 'nan-TW', confidence: 0.9 },
    ],
    asrMetadata: { serviceEndpoint: 'sagemaker', modelVersion: 'demo-hokkien-asr-v1', latencyMs: 850, language: 'nan-TW' },
    status: 'completed',
    traceId: 'demo-trace-001',
    audioS3Key: null,
    ttl: computeTtlEpochSeconds(RETENTION_DAYS.conversation),
  };

  const events: EventRecord[] = [
    {
      PK: Keys.elderPk(ELDER_ID),
      SK: Keys.eventSk(TODAY, 'demo-evt-meal'),
      GSI1PK: GSI1.pk(ELDER_ID, 'meal'),
      GSI1SK: GSI1.sk(TODAY),
      GSI2PK: GSI2.pk(ELDER_ID, 'auto_approved'),
      GSI2SK: GSI2.sk(TODAY, 'demo-evt-meal'),
      eventId: 'demo-evt-meal',
      elderId: ELDER_ID,
      eventType: 'meal',
      content: '中午吃了粥和菜脯',
      originalUtterance: '我今仔日中晝食糜佮菜脯，食了誠好食。',
      eventDate: TODAY,
      confidence: 0.86,
      sourceConversationId: CONVERSATION_ID,
      reviewStatus: 'auto_approved',
      reviewHistory: [],
      createdAt: NOW,
      updatedAt: NOW,
      ttl: computeTtlEpochSeconds(RETENTION_DAYS.event),
    },
    {
      PK: Keys.elderPk(ELDER_ID),
      SK: Keys.eventSk(TODAY, 'demo-evt-activity'),
      GSI1PK: GSI1.pk(ELDER_ID, 'activity'),
      GSI1SK: GSI1.sk(TODAY),
      GSI2PK: GSI2.pk(ELDER_ID, 'auto_approved'),
      GSI2SK: GSI2.sk(TODAY, 'demo-evt-activity'),
      eventId: 'demo-evt-activity',
      elderId: ELDER_ID,
      eventType: 'activity',
      content: '早上去公園散步半小時',
      originalUtterance: '有啦，透早有去公園行一下仔，行半點鐘。',
      eventDate: TODAY,
      confidence: 0.81,
      sourceConversationId: CONVERSATION_ID,
      reviewStatus: 'auto_approved',
      reviewHistory: [],
      createdAt: NOW,
      updatedAt: NOW,
      ttl: computeTtlEpochSeconds(RETENTION_DAYS.event),
    },
    {
      // Medication statements record only the elder's verbatim claim —
      // never an inferred adherence/effect judgement (B01.3).
      PK: Keys.elderPk(ELDER_ID),
      SK: Keys.eventSk(TODAY, 'demo-evt-medication'),
      GSI1PK: GSI1.pk(ELDER_ID, 'medication_statement'),
      GSI1SK: GSI1.sk(TODAY),
      GSI2PK: GSI2.pk(ELDER_ID, 'needs_review'),
      GSI2SK: GSI2.sk(TODAY, 'demo-evt-medication'),
      eventId: 'demo-evt-medication',
      elderId: ELDER_ID,
      eventType: 'medication_statement',
      content: '陳述今早已服用血壓藥',
      originalUtterance: '我早起有食血壓的藥仔矣。',
      eventDate: TODAY,
      confidence: 0.9,
      sourceConversationId: CONVERSATION_ID,
      reviewStatus: 'needs_review',
      reviewHistory: [],
      createdAt: NOW,
      updatedAt: NOW,
      ttl: computeTtlEpochSeconds(RETENTION_DAYS.event),
    },
  ];

  const confirmedMemory: MemoryRecord = {
    PK: Keys.elderPk(ELDER_ID),
    SK: Keys.confirmedMemorySk('demo-mem-tea'),
    memoryId: 'demo-mem-tea',
    elderId: ELDER_ID,
    category: 'preference',
    content: '喜歡喝烏龍茶',
    sourceConversationId: CONVERSATION_ID,
    confidence: 0.88,
    status: 'confirmed',
    confirmedBy: CAREGIVER_ID,
    confirmedAt: NOW,
    isActive: true,
    lastUsedAt: null,
    createdAt: NOW,
    updatedAt: NOW,
    auditTrail: [auditEntry('created', 'system', '從示範對話擷取'), auditEntry('confirmed', CAREGIVER_ID, '照服員確認')],
    ttl: null,
  };

  const summary: SummaryRecord = {
    PK: Keys.elderPk(ELDER_ID),
    SK: Keys.summarySk(TODAY),
    summaryId: 'demo-summary-001',
    elderId: ELDER_ID,
    date: TODAY,
    content: {
      overview: '今天精神狀況良好，飲食正常，有外出散步，並表示已服用血壓藥（待照服員覆核）。',
      meals: ['中午吃了粥和菜脯'],
      activities: ['早上去公園散步半小時'],
      sleep: null,
      medicationStatements: ['陳述今早已服用血壓藥'],
      importantEvents: [],
      emotionalState: '心情愉快',
    },
    sourceEventIds: events.map((e) => e.eventId),
    generatedAt: NOW,
    version: 1,
    ttl: computeTtlEpochSeconds(RETENTION_DAYS.summary),
    status: 'published',
    publishedAt: NOW,
    publishedBy: CAREGIVER_ID,
  };

  const records = [
    elder,
    persona,
    consent,
    caregiver,
    caregiverMapping,
    family,
    familyMapping,
    notificationPrefs,
    conversation,
    ...events,
    confirmedMemory,
    summary,
  ];

  for (const record of records) {
    await table.putItem(record);
  }

  console.log(`Seeded ${records.length} demo items for elder "${ELDER_ID}".`);
}

seed().catch((err) => {
  console.error('Demo data seed failed:', err);
  process.exitCode = 1;
});
