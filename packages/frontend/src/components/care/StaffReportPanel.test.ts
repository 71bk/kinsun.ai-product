// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiRequestError } from '@/lib/api/client';
import * as api from '@/lib/api/staff-reports';
import { listSummaries, type SummaryView } from '@/lib/api/summaries';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { StaffReportPanel } from './StaffReportPanel';

vi.mock('@/lib/api/staff-reports');
vi.mock('@/lib/api/summaries');
const report: api.StaffReport = {
  report_id: 'synthetic-report', elder_id: 'synthetic-elder', recipient_scope_ids: ['family-1'],
  report_type: 'DAILY', period_start: '2026-09-22', period_end: '2026-09-22', status: 'NEEDS_REVIEW',
  items: [{ category: 'MEAL', text: 'Synthetic reviewed meal', source_ids: ['summary-1'] }],
  data_gap_notice: 'Some activities were not mentioned.', sensitive_review_required: true,
  version: 2, published_at: null, withdrawn_at: null, updated_at: '2026-09-22T00:00:00Z',
};
const summary: SummaryView = {
  summaryId: 'summary-1', elderId: 'synthetic-elder', date: '2026-09-22', status: 'READY',
  items: [{ category: 'MEAL', text: 'Synthetic reviewed meal', sourceEventIds: ['event-1'], dataStatus: 'PRESENT' }],
  missingFields: ['SLEEP'], conflictFlags: [], version: 4, generatedAt: null, updatedAt: '2026-09-22T00:00:00Z',
};
const workspace = (): api.StaffReportWorkspace => ({
  recipients: [{ relationship_id: 'family-1', display_name: 'Synthetic family', share_scope: ['REPORT_DAILY'] }],
  reports: [report],
});
const config = { apiBaseUrl: '/backend/core' };
const accessCheck = vi.fn();
function setup(canPublish = true) {
  return render(createElement(LocaleProvider, { initialLocale: 'en', children:
    createElement(StaffReportPanel, { apiConfig: config, elderId: 'synthetic-elder',
      canPublish, canWithdraw: true, onAccessCheck: accessCheck }),
  }));
}
beforeEach(() => {
  vi.mocked(api.loadReportWorkspace).mockResolvedValue(workspace());
  vi.mocked(listSummaries).mockResolvedValue({ items: [summary] });
  vi.mocked(api.createReportFromSummary).mockResolvedValue(report);
  vi.mocked(api.commandStaffReport).mockResolvedValue({ ...report, status: 'PUBLISHED' });
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe('staff report human review workflow', () => {
  it('creates only from the chosen summary version and explicitly selected recipient', async () => {
    setup();
    await screen.findByLabelText('Choose a reviewed daily summary');
    const create = screen.getByRole('button', { name: 'Create report draft' }) as HTMLButtonElement;
    expect(create.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Choose a reviewed daily summary'), { target: { value: 'summary-1' } });
    expect(create.disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Synthetic family' }));
    fireEvent.click(create);
    await waitFor(() => expect(api.createReportFromSummary).toHaveBeenCalledOnce());
    expect(api.createReportFromSummary).toHaveBeenCalledWith(config, 'synthetic-elder', 'summary-1', 4,
      ['family-1'], expect.stringContaining('staff-report-draft-'));
    expect(api.commandStaffReport).not.toHaveBeenCalled();
    await screen.findByText('Draft created. Review its content below before publishing.');
  });

  it('does not publish on open, cancel or without explicit human review; publishes only after confirmation', async () => {
    setup();
    fireEvent.click(await screen.findByRole('button', { name: 'Review and publish' }));
    expect(api.commandStaffReport).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    expect(api.commandStaffReport).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Review and publish' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText('Synthetic reviewed meal')).toBeTruthy();
    expect(dialog.getByText(/Synthetic family/)).toBeTruthy();
    fireEvent.click(dialog.getByRole('button', { name: 'Review and publish' }));
    expect(api.commandStaffReport).not.toHaveBeenCalled();
    fireEvent.click(dialog.getByRole('checkbox'));
    fireEvent.click(dialog.getByRole('button', { name: 'Review and publish' }));
    await waitFor(() => expect(api.commandStaffReport).toHaveBeenCalledOnce());
    expect(api.commandStaffReport).toHaveBeenCalledWith(config, 'synthetic-elder', report, 'publish', expect.any(String));
    await screen.findByText('Report published.');
  });

  it('keeps a failed publication unconfirmed and reuses its idempotency key when retried', async () => {
    vi.mocked(api.commandStaffReport).mockRejectedValue(new ApiRequestError(503, 'private detail', 'UNAVAILABLE'));
    setup();
    fireEvent.click(await screen.findByRole('button', { name: 'Review and publish' }));
    const dialog = within(screen.getByRole('dialog'));
    fireEvent.click(dialog.getByRole('checkbox'));
    fireEvent.click(dialog.getByRole('button', { name: 'Review and publish' }));
    await dialog.findByRole('alert');
    expect(screen.queryByText('Report published.')).toBeNull();
    expect(screen.queryByText('private detail')).toBeNull();
    fireEvent.click(dialog.getByRole('button', { name: 'Review and publish' }));
    await waitFor(() => expect(api.commandStaffReport).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.commandStaffReport).mock.calls[0][4]).toBe(vi.mocked(api.commandStaffReport).mock.calls[1][4]);
  });

  it('hides private contents and closes the dialog when access is lost', async () => {
    vi.mocked(api.commandStaffReport).mockRejectedValue(new ApiRequestError(404, 'denied', 'RESOURCE_NOT_FOUND'));
    setup();
    fireEvent.click(await screen.findByRole('button', { name: 'Review and publish' }));
    const dialog = within(screen.getByRole('dialog'));
    fireEvent.click(dialog.getByRole('checkbox'));
    fireEvent.click(dialog.getByRole('button', { name: 'Review and publish' }));
    await screen.findByText('Report permission or family-sharing consent is currently unavailable.');
    expect(screen.queryByText('Synthetic reviewed meal')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(accessCheck).toHaveBeenCalledOnce();
  });

  it('requires confirmation before withdrawing a published report', async () => {
    vi.mocked(api.loadReportWorkspace).mockResolvedValue({ ...workspace(), reports: [{ ...report, status: 'PUBLISHED' }] });
    setup();
    fireEvent.click(await screen.findByRole('button', { name: 'Withdraw report' }));
    expect(api.commandStaffReport).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Withdraw report' }));
    await screen.findByText('Report withdrawn.');
    expect(vi.mocked(api.commandStaffReport).mock.calls[0][3]).toBe('withdraw');
  });

  it('does not expose publication controls without explicit permission', async () => {
    setup(false);
    await screen.findByText('Synthetic reviewed meal');
    expect(screen.queryByRole('button', { name: 'Review and publish' })).toBeNull();
  });

  it('disables publication if a draft recipient no longer has daily access', async () => {
    vi.mocked(api.loadReportWorkspace).mockResolvedValue({ ...workspace(), recipients: [] });
    setup();
    const publish = await screen.findByRole('button', { name: 'Review and publish' }) as HTMLButtonElement;
    expect(publish.disabled).toBe(true);
    fireEvent.click(publish);
    expect(api.commandStaffReport).not.toHaveBeenCalled();
  });
});
