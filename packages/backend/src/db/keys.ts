/**
 * DynamoDB single-table key builders. See design.md §DynamoDB Single-Table Design.
 * Every Elder-scoped item is keyed under PK = ELDER#{elderId}, which is what makes
 * elder-level data isolation (Property 11) enforceable by a single condition expression.
 */

export type ReviewStatusKey = 'auto_approved' | 'needs_review' | 'caregiver_confirmed' | 'caregiver_rejected';

export const Keys = {
  elderPk(elderId: string): string {
    return `ELDER#${elderId}`;
  },
  profileSk(): string {
    return 'PROFILE';
  },
  personaSk(): string {
    return 'PERSONA';
  },
  conversationSk(timestamp: string, conversationId: string): string {
    return `CONV#${timestamp}#${conversationId}`;
  },
  conversationSkPrefix(): string {
    return 'CONV#';
  },
  eventSk(date: string, eventId: string): string {
    return `EVENT#${date}#${eventId}`;
  },
  eventSkPrefix(): string {
    return 'EVENT#';
  },
  candidateMemorySk(memoryId: string): string {
    return `CMEM#${memoryId}`;
  },
  confirmedMemorySk(memoryId: string): string {
    return `MEM#${memoryId}`;
  },
  memorySkPrefix(kind: 'candidate' | 'confirmed'): string {
    return kind === 'candidate' ? 'CMEM#' : 'MEM#';
  },
  summarySk(date: string): string {
    return `SUM#${date}`;
  },
  summarySkPrefix(): string {
    return 'SUM#';
  },
  consentSk(type: string): string {
    return `CONSENT#${type}`;
  },

  caregiverPk(caregiverId: string): string {
    return `CG#${caregiverId}`;
  },
  caregiverElderMappingSk(elderId: string): string {
    return `ELDER#${elderId}`;
  },

  familyPk(familyId: string): string {
    return `FM#${familyId}`;
  },
  familyElderMappingSk(elderId: string): string {
    return `ELDER#${elderId}`;
  },
  notificationPrefSk(): string {
    return 'NOTIF_PREF';
  },

  auditPk(elderId: string): string {
    return `AUDIT#${elderId}`;
  },
  auditSk(timestamp: string, action: string): string {
    return `${timestamp}#${action}`;
  },

  /** Ephemeral WebSocket connection state — short TTL, not part of the durable domain model. */
  connectionPk(connectionId: string): string {
    return `CONN#${connectionId}`;
  },
  connectionSk(): string {
    return 'META';
  },
} as const;

/** GSI1: query events by elderId + eventType, ordered by date. */
export const GSI1 = {
  pk(elderId: string, eventType: string): string {
    return `ELDER#${elderId}#EVENT_TYPE#${eventType}`;
  },
  sk(date: string): string {
    return date;
  },
};

/** GSI2: query events by elderId + reviewStatus, ordered by date#eventId. */
export const GSI2 = {
  pk(elderId: string, reviewStatus: ReviewStatusKey): string {
    return `ELDER#${elderId}#REVIEW#${reviewStatus}`;
  },
  sk(date: string, eventId: string): string {
    return `${date}#${eventId}`;
  },
};

/** Extracts the elderId embedded in an `ELDER#{elderId}` partition key. Returns null if malformed. */
export function parseElderIdFromPk(pk: string): string | null {
  const match = /^ELDER#(.+)$/.exec(pk);
  return match ? match[1]! : null;
}
