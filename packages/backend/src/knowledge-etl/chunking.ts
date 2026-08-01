import { ulid } from 'ulid';

export interface DocumentChunk {
  chunkId: string;
  documentId: string;
  content: string;
  chunkIndex: number;
  totalChunks: number;
}

/** Normalizes raw document text before chunking (G02.1's "解析清理" stage). */
export function cleanText(raw: string): string {
  return raw
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/**
 * Splits cleaned text into overlapping chunks for embedding/indexing. A
 * fixed character budget (not tokens) keeps this dependency-free; overlap
 * preserves context across a chunk boundary so a fact split mid-sentence
 * is still retrievable from at least one chunk.
 */
export function splitIntoChunks(text: string, chunkSize = 500, overlap = 50): string[] {
  if (text.length === 0) return [];
  const chunks: string[] = [];
  let start = 0;
  while (start < text.length) {
    const end = Math.min(start + chunkSize, text.length);
    chunks.push(text.slice(start, end));
    if (end >= text.length) break;
    start = end - overlap;
  }
  return chunks;
}

/** Produces the Chunk JSONL records for one document (G02.1). */
export function buildChunks(documentId: string, rawText: string, chunkSize = 500, overlap = 50): DocumentChunk[] {
  const cleaned = cleanText(rawText);
  const pieces = splitIntoChunks(cleaned, chunkSize, overlap);
  return pieces.map((content, index) => ({
    chunkId: `chunk_${ulid()}`,
    documentId,
    content,
    chunkIndex: index,
    totalChunks: pieces.length,
  }));
}
