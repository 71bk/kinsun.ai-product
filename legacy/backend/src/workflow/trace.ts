import { ulid } from 'ulid';
import type { ErrorLog } from '@elderly-care/shared';

export function generateTraceId(): string {
  return `trace_${ulid()}`;
}

// PII patterns scrubbed from any free-text log message before it is written
// (J04.3 / Property 17). These are deliberately broad (over-redacting is
// safe; under-redacting a monitoring log is not).
const PII_PATTERNS: readonly RegExp[] = [
  /\b[A-Z][12]\d{8}\b/g, // Taiwan national ID (e.g. A123456789)
  /\b09\d{8}\b/g, // Taiwan mobile number
  /\b\d{2,4}-\d{6,8}\b/g, // Taiwan landline
  /[\w.+-]+@[\w-]+\.[\w.-]+/g, // email
];

export function redactPii(text: string): string {
  return PII_PATTERNS.reduce((acc, pattern) => acc.replace(pattern, '[REDACTED]'), text);
}

export interface CreateErrorLogParams {
  traceId: string;
  component: ErrorLog['component'];
  errorType: ErrorLog['errorType'];
  errorCode: string;
  message: string;
  elderId: string;
  retryAttempt: number;
  resolved: boolean;
  fallbackAction: string;
}

/**
 * Builds a CloudWatch-ready ErrorLog. `message` is always redacted and the
 * shape intentionally has no field for names/transcripts/national IDs —
 * only opaque IDs — so PII can only leak through free text, which this
 * scrubs (Property 17).
 */
export function createErrorLog(params: CreateErrorLogParams): ErrorLog {
  return {
    traceId: params.traceId,
    timestamp: new Date().toISOString(),
    component: params.component,
    errorType: params.errorType,
    errorCode: params.errorCode,
    message: redactPii(params.message),
    elderId: params.elderId,
    retryAttempt: params.retryAttempt,
    resolved: params.resolved,
    fallbackAction: params.fallbackAction,
  };
}
