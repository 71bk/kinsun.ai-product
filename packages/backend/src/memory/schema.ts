import { z } from 'zod';

/** Property 7 gate for candidate memories: sourceConversationId, createdAt, confidence are mandatory (D01.3). */
export const CandidateMemorySchema = z.object({
  memoryId: z.string().min(1),
  elderId: z.string().min(1),
  category: z.enum(['preference', 'relationship', 'routine', 'health_condition', 'life_event']),
  content: z.string().min(1),
  sourceConversationId: z.string().min(1),
  confidence: z.number().min(0).max(1),
  createdAt: z.string().min(1),
  status: z.enum(['pending', 'confirmed', 'rejected']),
});

export type ValidatedCandidateMemory = z.infer<typeof CandidateMemorySchema>;

export type ValidationResult =
  | { success: true; data: ValidatedCandidateMemory }
  | { success: false; errors: string[] };

export function validateCandidateMemory(candidate: unknown): ValidationResult {
  const result = CandidateMemorySchema.safeParse(candidate);
  if (result.success) return { success: true, data: result.data };
  return { success: false, errors: result.error.issues.map((issue) => `${issue.path.join('.')}: ${issue.message}`) };
}
