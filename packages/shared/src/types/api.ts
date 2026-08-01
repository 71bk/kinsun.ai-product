import type { EventType, ReviewStatus, UserRole } from './enums.js';
import type { CandidateMemory, ConfirmedMemory, PersonaContext } from './entities.js';

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

/** Resolved per-request identity, produced by the Lambda Authorizer. See H01. */
export interface AuthorizationContext {
  userId: string;
  role: UserRole;
  authorizedElderIds: string[];
  tenantId: string;
}

// ---------------------------------------------------------------------------
// POST /v1/conversations/start
// ---------------------------------------------------------------------------

export interface StartConversationRequest {
  elderId: string;
}

export interface StartConversationResponse {
  conversationId: string;
  traceId: string;
  websocketUrl: string;
}

// ---------------------------------------------------------------------------
// GET /v1/elders/{elderId}/events
// ---------------------------------------------------------------------------

export interface ListEventsRequest {
  elderId: string;
  dateFrom?: string;
  dateTo?: string;
  eventType?: EventType;
  reviewStatus?: ReviewStatus;
  cursor?: string;
  limit?: number;
}

export interface ListEventsResponse {
  items: EventSummary[];
  nextCursor: string | null;
}

export interface EventSummary {
  eventId: string;
  eventType: EventType;
  content: string;
  eventDate: string;
  confidence: number;
  reviewStatus: ReviewStatus;
  sourceConversationId: string;
  /** Count of prior caregiver corrections — the UI links to the full before/after history (B03.2, B04.3). */
  correctionCount: number;
}

// ---------------------------------------------------------------------------
// PUT /v1/events/{eventId}
// ---------------------------------------------------------------------------

export interface UpdateEventRequest {
  /** Single-table design keys events under ELDER#{elderId}; the route has no elderId segment, so it travels in the body. */
  elderId: string;
  eventDate: string;
  content?: string;
  eventType?: EventType;
  reviewStatus?: ReviewStatus;
  updatedBy: string;
}

// ---------------------------------------------------------------------------
// Memory endpoints
// ---------------------------------------------------------------------------

/** GET /v1/elders/{elderId}/memories — candidates awaiting confirm/reject, plus already-confirmed ones. */
export interface ListMemoriesResponse {
  candidates: CandidateMemory[];
  confirmed: ConfirmedMemory[];
}

export interface ConfirmMemoryRequest {
  /** No elderId path segment on this route, so it travels in the body (same reasoning as UpdateEventRequest). */
  elderId: string;
  confirmerId: string;
}

export interface RejectMemoryRequest {
  elderId: string;
  rejecterId: string;
}

// ---------------------------------------------------------------------------
// GET /v1/elders/{elderId}/summaries
// ---------------------------------------------------------------------------

export interface ListSummariesRequest {
  elderId: string;
  dateFrom?: string;
  dateTo?: string;
}

// ---------------------------------------------------------------------------
// POST /v1/search/health
// ---------------------------------------------------------------------------

export interface HealthSearchRequest {
  elderId: string;
  question: string;
}

export interface HealthSearchResponse {
  answer: string;
  sources: { documentTitle: string; sourceAgency: string; chunkId: string }[];
  disclaimer: string;
  grounded: boolean;
}

// ---------------------------------------------------------------------------
// GET /v1/elders/{elderId}/reports
// ---------------------------------------------------------------------------

export interface GetReportRequest {
  elderId: string;
  range: 'week' | 'year';
}

export interface ReportResponse {
  range: 'week' | 'year';
  dateFrom: string;
  dateTo: string;
  eventCountByType: Record<EventType, number>;
  totalInteractions: number;
  /** A short voice-friendly narrative for "長者以語音詢問生活紀錄" (A07.3). */
  voiceSummary: string;
}

// ---------------------------------------------------------------------------
// GET /v1/caregivers/{caregiverId}/dashboard
// ---------------------------------------------------------------------------

export interface CaregiverDashboardEntry {
  elderId: string;
  elderName: string;
  lastInteractionAt: string | null;
  todayInteractionCount: number;
  summaryStatus: 'generated' | 'pending' | 'failed';
  pendingReviewCount: number;
}

export interface CaregiverDashboardResponse {
  elders: CaregiverDashboardEntry[];
}

// ---------------------------------------------------------------------------
// PUT /v1/elders/{elderId}/persona
// ---------------------------------------------------------------------------

export type UpdatePersonaRequest = Partial<PersonaContext> & { updatedBy: string };

// ---------------------------------------------------------------------------
// Consent
// ---------------------------------------------------------------------------

export interface ConsentRequest {
  elderId: string;
  type: 'recording' | 'data_processing';
}

// ---------------------------------------------------------------------------
// Generic API error shape
// ---------------------------------------------------------------------------

export interface ApiError {
  code: string;
  message: string;
  traceId?: string;
}
