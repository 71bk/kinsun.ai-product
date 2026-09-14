import { apiFetch, ApiRequestError, type ApiConfig } from './client';

export interface ServiceRecordView {
  service_record_id: string;
  assignment_id: string;
  content: string;
  service_date: string;
  service_timezone: string;
  completed_at: string;
  status: 'COMPLETED';
  version: 1;
}

export interface ServiceRecordSubmission {
  expected_assignment_version: number;
  content: string;
}

export interface ServiceRecordCompletion {
  service_record_id: string;
  assignment_id: string;
  assignment_version: number;
  status: 'COMPLETED';
}

export async function submitServiceRecordAndComplete(
  config: ApiConfig,
  assignmentId: string,
  submission: ServiceRecordSubmission,
  key: string,
): Promise<ServiceRecordCompletion> {
  const value = await apiFetch<ServiceRecordCompletion>(
    config,
    `/api/v1/home-care/assignments/${encodeURIComponent(assignmentId)}/service-record/complete`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body: JSON.stringify({
        expected_assignment_version: submission.expected_assignment_version,
        content: submission.content,
        record_type: 'SERVICE_NOTE',
      }),
    },
  );
  if (
    !value ||
    Object.keys(value).some(
      (field) =>
        !['service_record_id', 'assignment_id', 'assignment_version', 'status'].includes(field),
    ) ||
    value.assignment_id !== assignmentId ||
    typeof value.service_record_id !== 'string' ||
    !value.service_record_id ||
    value.status !== 'COMPLETED' ||
    value.assignment_version !== submission.expected_assignment_version + 1
  )
    throw new ApiRequestError(502, 'Invalid service completion response');
  return value;
}

function toView(value: ServiceRecordView, assignmentId: string): ServiceRecordView {
  if (
    !value ||
    value.assignment_id !== assignmentId ||
    value.status !== 'COMPLETED' ||
    value.version !== 1 ||
    typeof value.content !== 'string' ||
    !value.content.trim() ||
    Array.from(value.content).length > 4000 ||
    typeof value.service_record_id !== 'string' ||
    typeof value.service_date !== 'string' ||
    typeof value.service_timezone !== 'string' ||
    !Number.isFinite(Date.parse(value.completed_at))
  ) {
    throw new ApiRequestError(502, 'Invalid service record response');
  }
  return {
    service_record_id: value.service_record_id,
    assignment_id: value.assignment_id,
    content: value.content,
    service_date: value.service_date,
    service_timezone: value.service_timezone,
    completed_at: value.completed_at,
    status: value.status,
    version: value.version,
  };
}

export async function getServiceRecord(config: ApiConfig, assignmentId: string) {
  return toView(
    await apiFetch<ServiceRecordView>(
      config,
      `/api/v1/home-care/assignments/${encodeURIComponent(assignmentId)}/service-record`,
      { cache: 'no-store' },
    ),
    assignmentId,
  );
}

export async function submitServiceRecord(
  config: ApiConfig,
  assignmentId: string,
  submission: ServiceRecordSubmission,
  key: string,
) {
  return toView(
    await apiFetch<ServiceRecordView>(
      config,
      `/api/v1/home-care/assignments/${encodeURIComponent(assignmentId)}/service-record`,
      {
        method: 'POST',
        headers: { 'Idempotency-Key': key },
        body: JSON.stringify({
          expected_assignment_version: submission.expected_assignment_version,
          content: submission.content,
          record_type: 'SERVICE_NOTE',
        }),
      },
    ),
    assignmentId,
  );
}
