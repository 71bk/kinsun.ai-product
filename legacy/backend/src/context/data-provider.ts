import type { MemoryRecord, PersonaContext, PersonaRecord, SummaryRecord } from '@elderly-care/shared';
import { DynamoTable, Keys } from '../db/index.js';
import type { ContextComposeInputs, SituationalContext } from './types.js';

const DEFAULT_PERSONA: PersonaContext = {
  displayName: '朋友',
  preferredLanguage: 'zh-TW',
  responseLength: 'medium',
  speakingSpeed: 'normal',
  interactionStyle: 'warm',
  customGreeting: '',
};

function toPersonaContext(record: PersonaRecord | null): PersonaContext {
  if (!record) return DEFAULT_PERSONA;
  return {
    displayName: record.displayName,
    preferredLanguage: record.preferredLanguage,
    responseLength: record.responseLength,
    speakingSpeed: record.speakingSpeed,
    interactionStyle: record.interactionStyle,
    customGreeting: record.customGreeting,
  };
}

function buildSituationalContext(recentInteractionCount: number, lastInteractionTime: string | null): SituationalContext {
  const now = new Date();
  return {
    currentTime: now.toISOString(),
    dayOfWeek: now.toLocaleDateString('en-US', { weekday: 'long' }),
    weather: null, // no weather provider wired up yet — see design.md's WeatherInfo hook
    recentInteractionCount,
    lastInteractionTime,
  };
}

/**
 * Fetches everything ContextComposer needs for one elder from DynamoDB.
 * Kept separate from ContextComposer itself (composer.ts) so the packing/
 * filtering logic stays unit-testable without a database (see
 * composer.property.test.ts) while this module is the real I/O boundary
 * used at runtime by context-handler.ts.
 */
export async function loadContextInputs(elderId: string, table: DynamoTable = new DynamoTable()): Promise<ContextComposeInputs> {
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);

  const [personaRecord, confirmedMemories, todaySummary, yesterdaySummary, conversations] = await Promise.all([
    table.getItem<PersonaRecord>(Keys.elderPk(elderId), Keys.personaSk()),
    table.queryByPk<MemoryRecord>(Keys.elderPk(elderId), Keys.memorySkPrefix('confirmed')),
    table.getItem<SummaryRecord>(Keys.elderPk(elderId), Keys.summarySk(today)),
    table.getItem<SummaryRecord>(Keys.elderPk(elderId), Keys.summarySk(yesterday)),
    table.queryByPk<{ startTime: string }>(Keys.elderPk(elderId), Keys.conversationSkPrefix()),
  ]);

  const recentSummary = todaySummary?.content.overview ?? yesterdaySummary?.content.overview ?? null;
  const recentInteractionCount = conversations.filter((c) => c.startTime.startsWith(today)).length;
  const lastInteractionTime = conversations.reduce<string | null>(
    (latest, c) => (!latest || c.startTime > latest ? c.startTime : latest),
    null,
  );

  return {
    persona: toPersonaContext(personaRecord),
    recentSummary,
    memories: confirmedMemories,
    situationalContext: buildSituationalContext(recentInteractionCount, lastInteractionTime),
    searchResults: [],
  };
}
