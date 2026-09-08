// Core authority: contracts/schemas/common/{ResponseMetaV1,ErrorEnvelopeV1}.json.
// BFF errors intentionally have a different shape: lib/server/bff-response.ts.
// This validates the transport envelope, not each endpoint's domain DTO.
interface ResponseMeta {
  correlation_id: string;
  timestamp: string;
  schema_version: '1.0';
}

interface ErrorFields {
  code: string;
  message: string;
  reason_code: string | null;
  retryable: boolean;
}

const CORE_ERROR_CODES = new Set([
  'bad_request', 'authentication_required', 'forbidden', 'not_found',
  'conflict', 'validation_error', 'internal_error', 'service_unavailable',
]);
const BFF_ERROR_CODES = new Set([
  'bad_request', 'unauthorized', 'forbidden', 'payload_too_large',
  'bad_gateway', 'gateway_timeout',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  return Object.keys(value).length === expected.length &&
    expected.every((key) => Object.hasOwn(value, key));
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

function isDateTime(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  // Date.parse alone accepts date-only strings and normalizes impossible dates.
  const match = /^(\d{4})-(\d{2})-(\d{2})T([01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/i.exec(value);
  if (!match || Number.isNaN(Date.parse(value))) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1];
}

function isResponseMeta(value: unknown): value is ResponseMeta {
  return isRecord(value) &&
    hasExactKeys(value, ['correlation_id', 'timestamp', 'schema_version']) &&
    isNonEmptyString(value.correlation_id) &&
    isDateTime(value.timestamp) &&
    value.schema_version === '1.0';
}

export function isSuccessEnvelope(value: unknown): value is { data: unknown; meta: ResponseMeta } {
  return isRecord(value) && hasExactKeys(value, ['data', 'meta']) && isResponseMeta(value.meta);
}

function isErrorFields(value: Record<string, unknown>): boolean {
  return isNonEmptyString(value.code) &&
    isNonEmptyString(value.message) &&
    (value.reason_code === null ||
      (isNonEmptyString(value.reason_code) && [...value.reason_code].length <= 120)) &&
    typeof value.retryable === 'boolean';
}

function isValidationDetail(value: unknown): boolean {
  return isRecord(value) && hasExactKeys(value, ['field', 'reason']) &&
    typeof value.field === 'string' && typeof value.reason === 'string';
}

export function isErrorEnvelope(value: unknown): value is { error: ErrorFields } {
  if (!isRecord(value) || !isRecord(value.error) || !isErrorFields(value.error)) return false;
  const error = value.error;

  if (hasExactKeys(value, ['error'])) {
    return hasExactKeys(error, [
      'code', 'message', 'correlation_id', 'reason_code', 'retryable', 'details',
    ]) && CORE_ERROR_CODES.has(error.code as string) &&
      isNonEmptyString(error.correlation_id) &&
      (error.details === null ||
        (Array.isArray(error.details) && error.details.every(isValidationDetail)));
  }

  // Validate BFF errors independently; do not weaken the Core schema to fit them.
  return hasExactKeys(value, ['error', 'meta']) && isResponseMeta(value.meta) &&
    hasExactKeys(error, ['code', 'message', 'reason_code', 'retryable']) &&
    BFF_ERROR_CODES.has(error.code as string) && isNonEmptyString(error.reason_code);
}
