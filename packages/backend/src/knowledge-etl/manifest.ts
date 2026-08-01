import { ulid } from 'ulid';
import { z } from 'zod';

/** Property-adjacent gate for G01.2: a document with no source info can never enter the pipeline. */
export const DocumentManifestInputSchema = z.object({
  sourceAgency: z.string().min(1, 'sourceAgency is required — documents without a source are rejected (G01.2)'),
  title: z.string().min(1),
  version: z.string().min(1),
  region: z.string().min(1),
  license: z.string().min(1),
  serviceType: z.string().min(1),
  riskLevel: z.enum(['low', 'medium', 'high']),
  effectiveDate: z.string().min(1),
  expiryDate: z.string().nullable().optional(),
});

export type DocumentManifestInput = z.infer<typeof DocumentManifestInputSchema>;

export interface DocumentManifest extends DocumentManifestInput {
  documentId: string;
  createdAt: string;
}

export class RejectedDocumentError extends Error {
  constructor(public readonly errors: string[]) {
    super(`Document rejected — manifest is invalid: ${errors.join('; ')}`);
    this.name = 'RejectedDocumentError';
  }
}

/** Registers a source document (G01.1). Throws RejectedDocumentError for any document missing source info. */
export function createManifest(input: unknown): DocumentManifest {
  const result = DocumentManifestInputSchema.safeParse(input);
  if (!result.success) {
    throw new RejectedDocumentError(result.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`));
  }
  return {
    ...result.data,
    documentId: `doc_${ulid()}`,
    createdAt: new Date().toISOString(),
  };
}
