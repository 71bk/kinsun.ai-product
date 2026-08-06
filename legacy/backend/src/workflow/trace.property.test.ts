import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import type { ErrorLog } from '@elderly-care/shared';
import { createErrorLog, generateTraceId, redactPii } from './trace.js';

const componentArb = fc.constantFrom<ErrorLog['component']>(
  'asr',
  'context',
  'llm',
  'guardrail_check',
  'tts',
  'event_extractor',
  'memory',
);

/**
 * Feature: elderly-care-ai-companion, Property 16: Trace ID 傳播一致性.
 * For any complete voice interaction, every stage's log record (ASR ->
 * Context Compose -> LLM -> Guardrail -> TTS -> Event Extract) must carry
 * the same trace ID.
 */
describe('Property 16: Trace ID propagation consistency', () => {
  it('every stage log in a simulated pipeline carries the same traceId', () => {
    fc.assert(
      fc.property(
        fc.array(componentArb, { minLength: 1, maxLength: 8 }),
        fc.string({ minLength: 1, maxLength: 8 }),
        (stages, elderId) => {
          const traceId = generateTraceId();
          // Simulate the pipeline: every Lambda in the chain receives and
          // re-emits the same traceId from the incoming event payload.
          const logs = stages.map((component, i) =>
            createErrorLog({
              traceId,
              component,
              errorType: 'timeout',
              errorCode: 'E1',
              message: 'stage ran',
              elderId,
              retryAttempt: 0,
              resolved: i === stages.length - 1,
              fallbackAction: 'none',
            }),
          );
          const uniqueTraceIds = new Set(logs.map((l) => l.traceId));
          expect(uniqueTraceIds.size).toBe(1);
          expect(uniqueTraceIds.has(traceId)).toBe(true);
        },
      ),
      { numRuns: 200 },
    );
  });

  it('distinct interactions get distinct trace IDs', () => {
    const ids = new Set(Array.from({ length: 1000 }, () => generateTraceId()));
    expect(ids.size).toBe(1000);
  });
});

/**
 * Feature: elderly-care-ai-companion, Property 17: 監控日誌 PII 去除.
 * For any log message containing a PII pattern, the persisted CloudWatch
 * record must not contain that pattern — only opaque IDs (event ID, trace
 * ID) survive.
 */
describe('Property 17: Monitoring log PII removal', () => {
  const taiwanIdArb = fc
    .tuple(fc.constantFrom(...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), fc.constantFrom('1', '2'), fc.stringMatching(/^\d{8}$/))
    .map(([letter, gender, digits]) => `${letter}${gender}${digits}`);
  const phoneArb = fc.stringMatching(/^09\d{8}$/);
  const emailArb = fc
    .tuple(fc.stringMatching(/^[a-z]{3,8}$/), fc.stringMatching(/^[a-z]{3,8}$/))
    .map(([user, domain]) => `${user}@${domain}.com`);

  it('strips Taiwan national ID numbers from log messages', () => {
    fc.assert(
      fc.property(taiwanIdArb, fc.string(), (id, prefix) => {
        const redacted = redactPii(`${prefix} ${id} 備註`);
        expect(redacted).not.toContain(id);
      }),
      { numRuns: 100 },
    );
  });

  it('strips phone numbers and emails from log messages', () => {
    fc.assert(
      fc.property(phoneArb, emailArb, (phone, email) => {
        const redacted = redactPii(`聯絡方式 ${phone} 或 ${email}`);
        expect(redacted).not.toContain(phone);
        expect(redacted).not.toContain(email);
      }),
      { numRuns: 100 },
    );
  });

  it('createErrorLog redacts PII embedded in the message field end-to-end', () => {
    const log = createErrorLog({
      traceId: 'trace_1',
      component: 'asr',
      errorType: 'validation_error',
      errorCode: 'E1',
      message: '長者說身分證字號是 A123456789，電話 0912345678',
      elderId: 'elder-1',
      retryAttempt: 0,
      resolved: false,
      fallbackAction: 'none',
    });
    expect(log.message).not.toContain('A123456789');
    expect(log.message).not.toContain('0912345678');
  });
});
