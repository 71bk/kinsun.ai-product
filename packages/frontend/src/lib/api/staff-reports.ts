import { apiFetch, type ApiConfig } from './client';
import type { FamilyReportStatus, FamilyReportType } from './family-report-types';

export interface StaffReport {
  report_id: string;
  elder_id: string;
  recipient_scope_ids: string[];
  report_type: FamilyReportType;
  period_start: string;
  period_end: string;
  status: FamilyReportStatus;
  items: { category: string; text: string; source_ids: string[] }[];
  data_gap_notice: string | null;
  sensitive_review_required: boolean;
  version: number;
  published_at: string | null;
  withdrawn_at: string | null;
  updated_at: string;
}
export interface ReportRecipient {
  relationship_id: string;
  display_name: string;
  share_scope: string[];
}
export interface StaffReportWorkspace {
  recipients: ReportRecipient[];
  reports: StaffReport[];
}
export function loadReportWorkspace(config: ApiConfig, elderId: string) {
  return apiFetch<StaffReportWorkspace>(config, '/api/v1/elders/' + elderId + '/family-report-workspace');
}
export function createReportFromSummary(
  config: ApiConfig, elderId: string, summaryId: string, expectedVersion: number,
  recipients: string[], key: string,
) {
  return apiFetch<StaffReport>(config, '/api/v1/elders/' + elderId + '/family-reports/from-summary', {
    method: 'POST', headers: { 'Idempotency-Key': key },
    body: JSON.stringify({ summary_id: summaryId, expected_summary_version: expectedVersion,
      recipient_scope_ids: recipients }),
  });
}
export function commandStaffReport(
  config: ApiConfig, elderId: string, report: StaffReport, action: 'publish' | 'withdraw', key: string,
) {
  return apiFetch<StaffReport>(config, '/api/v1/elders/' + elderId + '/family-reports/' + report.report_id + '/' + action, {
    method: 'POST', headers: { 'Idempotency-Key': key },
    body: JSON.stringify({ expected_version: report.version,
      reason_code: action === 'publish' ? 'CAREGIVER_UI_SAFETY_REVIEW' : 'CAREGIVER_UI_WITHDRAWAL',
      ...(action === 'publish' ? { safety_review_passed: true } : {}),
    }),
  });
}
