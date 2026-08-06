import { describe, expect, it, vi } from 'vitest';
import { RejectedDocumentError, createManifest } from './manifest.js';
import { buildChunks } from './chunking.js';
import { tagMetadata } from './metadata.js';
import { ingestDocument } from './pipeline.js';
import { KnowledgeIndexWriter } from './index-writer.js';

const validManifestInput = {
  sourceAgency: '衛生福利部',
  title: '長者衛教手冊',
  version: '1.0',
  region: 'TW',
  license: 'CC-BY-4.0',
  serviceType: 'health',
  riskLevel: 'low' as const,
  effectiveDate: '2026-01-01',
};

describe('createManifest (G01.1, G01.2)', () => {
  it('creates a manifest for a document with complete source info', () => {
    const manifest = createManifest(validManifestInput);
    expect(manifest.sourceAgency).toBe('衛生福利部');
    expect(manifest.documentId).toMatch(/^doc_/);
  });

  it('rejects a document missing sourceAgency', () => {
    const { sourceAgency: _omit, ...withoutSource } = validManifestInput;
    expect(() => createManifest(withoutSource)).toThrow(RejectedDocumentError);
  });

  it('rejects a document with an empty-string sourceAgency', () => {
    expect(() => createManifest({ ...validManifestInput, sourceAgency: '' })).toThrow(RejectedDocumentError);
  });
});

describe('buildChunks', () => {
  it('splits long text into multiple overlapping chunks, all traceable to the same documentId', () => {
    const longText = '長者衛教內容。'.repeat(200);
    const chunks = buildChunks('doc_1', longText, 100, 20);
    expect(chunks.length).toBeGreaterThan(1);
    for (const chunk of chunks) {
      expect(chunk.documentId).toBe('doc_1');
      expect(chunk.totalChunks).toBe(chunks.length);
    }
  });

  it('normalizes whitespace before chunking', () => {
    const chunks = buildChunks('doc_1', '第一行\r\n\r\n\r\n第二行   有多個空格');
    expect(chunks[0]!.content).not.toContain('\r');
    expect(chunks[0]!.content).not.toContain('   ');
  });
});

describe('tagMetadata (G02.2)', () => {
  it('always defaults review_status to needs_review, regardless of manifest content', () => {
    const manifest = createManifest(validManifestInput);
    const metadata = tagMetadata(manifest);
    expect(metadata.reviewStatus).toBe('needs_review');
  });
});

describe('ingestDocument pipeline', () => {
  it('rejects sourceless input before ever calling the index writer', async () => {
    const writer = new KnowledgeIndexWriter({
      client: { index: vi.fn() } as never,
      bedrockClient: {} as never,
    });
    const writeSpy = vi.spyOn(writer, 'writeChunks');

    await expect(
      ingestDocument({ manifest: { ...validManifestInput, sourceAgency: '' }, rawText: '內容' }, writer),
    ).rejects.toThrow(RejectedDocumentError);
    expect(writeSpy).not.toHaveBeenCalled();
  });

  it('produces needs_review chunks for a valid document', async () => {
    const writer = new KnowledgeIndexWriter({ client: {} as never, bedrockClient: {} as never });
    vi.spyOn(writer, 'writeChunks').mockResolvedValue();

    const result = await ingestDocument({ manifest: validManifestInput, rawText: '長者衛教內容' }, writer);
    expect(result.manifest.sourceAgency).toBe('衛生福利部');
    expect(result.chunks.length).toBeGreaterThan(0);
    expect(writer.writeChunks).toHaveBeenCalledWith(
      result.chunks,
      expect.objectContaining({ reviewStatus: 'needs_review' }),
      '長者衛教手冊',
    );
  });
});
