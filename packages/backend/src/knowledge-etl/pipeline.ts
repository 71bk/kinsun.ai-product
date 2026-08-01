import { buildChunks, type DocumentChunk } from './chunking.js';
import { KnowledgeIndexWriter } from './index-writer.js';
import { createManifest, type DocumentManifest } from './manifest.js';
import { tagMetadata } from './metadata.js';

export interface IngestDocumentInput {
  manifest: unknown; // validated by createManifest — see manifest.ts for required fields
  rawText: string;
}

export interface IngestDocumentResult {
  manifest: DocumentManifest;
  chunks: DocumentChunk[];
}

/**
 * Full ingestion pipeline (G02.1): 來源登錄 (createManifest, rejects
 * sourceless docs) → 解析清理 + Chunk JSONL 產生 (buildChunks) → Metadata 標註
 * (tagMetadata, always needs_review) → Embedding/Index 建立 (KnowledgeIndexWriter).
 * There is deliberately no step here that flips review_status to
 * 'approved' — that only happens via a separate human-review action.
 */
export async function ingestDocument(
  input: IngestDocumentInput,
  indexWriter: KnowledgeIndexWriter = new KnowledgeIndexWriter(),
): Promise<IngestDocumentResult> {
  const manifest = createManifest(input.manifest); // throws RejectedDocumentError if sourceless
  const chunks = buildChunks(manifest.documentId, input.rawText);
  const metadata = tagMetadata(manifest);

  await indexWriter.writeChunks(chunks, metadata, manifest.title);

  return { manifest, chunks };
}
