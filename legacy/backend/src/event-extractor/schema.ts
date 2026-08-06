import { z } from 'zod';

/**
 * Property 6 (結構化輸出 Schema 驗證閘門) / Property 7 (實體必要欄位完整性):
 * this schema is the single gate every candidate event must pass before it
 * can be persisted. Every field is required and non-empty — a candidate
 * missing any one of them fails validation and is never written to
 * DynamoDB, regardless of how it was produced (B01.2, B01.4).
 */
export const EventTypeEnum = z.enum(['meal', 'activity', 'sleep', 'medication_statement', 'emotion', 'important_event']);
export const ReviewStatusEnum = z.enum(['auto_approved', 'needs_review', 'caregiver_confirmed', 'caregiver_rejected']);

export const ExtractedEventSchema = z.object({
  eventId: z.string().min(1),
  elderId: z.string().min(1),
  eventType: EventTypeEnum,
  content: z.string().min(1),
  originalUtterance: z.string().min(1),
  eventDate: z.string().min(1),
  confidence: z.number().min(0).max(1),
  sourceConversationId: z.string().min(1),
  reviewStatus: ReviewStatusEnum,
  createdAt: z.string().min(1),
  metadata: z.record(z.string(), z.unknown()),
});

export type ValidatedExtractedEvent = z.infer<typeof ExtractedEventSchema>;

export type ValidationResult =
  | { success: true; data: ValidatedExtractedEvent }
  | { success: false; errors: string[] };

export function validateExtractedEvent(candidate: unknown): ValidationResult {
  const result = ExtractedEventSchema.safeParse(candidate);
  if (result.success) {
    return { success: true, data: result.data };
  }
  return { success: false, errors: result.error.issues.map((issue) => `${issue.path.join('.')}: ${issue.message}`) };
}
