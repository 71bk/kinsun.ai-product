import { apiFetch, ApiRequestError, type ApiConfig } from './client';
import { assertNoRestrictedFields } from './family-guard';

export interface FamilyLinePreference {
  schema_version: '1.0';
  elder_id: string;
  preference_id: string | null;
  line_enabled: boolean;
  version: number;
  frequency: 'DAILY';
  send_time_local: '08:00';
  timezone: 'Asia/Taipei';
  line_status: 'UNLINKED' | 'LINKED' | 'RELINK_REQUIRED';
  availability: 'READY' | 'LINE_LINK_REQUIRED' | 'SERVICE_UNAVAILABLE' | 'UNSUPPORTED_SCHEDULE';
  line_link_available: boolean;
  can_enable: boolean;
  updated_at: string | null;
}

const FIELDS = [
  'schema_version',
  'elder_id',
  'preference_id',
  'line_enabled',
  'version',
  'frequency',
  'send_time_local',
  'timezone',
  'line_status',
  'availability',
  'line_link_available',
  'can_enable',
  'updated_at',
];
const UUID_PATTERN = /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i;

function validate(raw: unknown, elderId: string): FamilyLinePreference {
  assertNoRestrictedFields(raw);
  const data = raw as FamilyLinePreference;
  if (
    !data ||
    typeof data !== 'object' ||
    Array.isArray(data) ||
    Object.keys(data).length !== FIELDS.length ||
    Object.keys(data).some((key) => !FIELDS.includes(key)) ||
    data.schema_version !== '1.0' ||
    data.elder_id !== elderId ||
    !UUID_PATTERN.test(data.elder_id) ||
    !(
      data.preference_id === null ||
      (typeof data.preference_id === 'string' && UUID_PATTERN.test(data.preference_id))
    ) ||
    !Number.isInteger(data.version) ||
    data.version < 0 ||
    (data.preference_id === null) !== (data.version === 0) ||
    typeof data.line_enabled !== 'boolean' ||
    typeof data.can_enable !== 'boolean' ||
    typeof data.line_link_available !== 'boolean' ||
    data.frequency !== 'DAILY' ||
    data.send_time_local !== '08:00' ||
    data.timezone !== 'Asia/Taipei' ||
    !['UNLINKED', 'LINKED', 'RELINK_REQUIRED'].includes(data.line_status) ||
    !['READY', 'LINE_LINK_REQUIRED', 'SERVICE_UNAVAILABLE', 'UNSUPPORTED_SCHEDULE'].includes(
      data.availability,
    ) ||
    data.can_enable !== (data.availability === 'READY') ||
    (data.can_enable && (data.line_status !== 'LINKED' || !data.line_link_available)) ||
    !(
      data.updated_at === null ||
      (typeof data.updated_at === 'string' && Number.isFinite(Date.parse(data.updated_at)))
    )
  ) {
    throw new ApiRequestError(
      502,
      'Invalid notification settings response',
      'MALFORMED_API_RESPONSE',
    );
  }
  return data;
}

export async function getFamilyLinePreference(
  config: ApiConfig,
  elderId: string,
  signal?: AbortSignal,
) {
  return validate(
    await apiFetch<unknown>(
      config,
      `/api/v1/family/elders/${encodeURIComponent(elderId)}/line-notification-preference`,
      { signal, cache: 'no-store' },
    ),
    elderId,
  );
}

export async function updateFamilyLinePreference(
  config: ApiConfig,
  elderId: string,
  lineEnabled: boolean,
  expectedVersion: number,
  idempotencyKey: string,
  signal?: AbortSignal,
) {
  return validate(
    await apiFetch<unknown>(
      config,
      `/api/v1/family/elders/${encodeURIComponent(elderId)}/line-notification-preference`,
      {
        method: 'PUT',
        headers: { 'Idempotency-Key': idempotencyKey },
        signal,
        body: JSON.stringify({ line_enabled: lineEnabled, expected_version: expectedVersion }),
      },
    ),
    elderId,
  );
}
