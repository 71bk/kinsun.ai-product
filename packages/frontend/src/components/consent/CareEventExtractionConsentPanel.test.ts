// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { activeCareEventExtractionConsent, type ConsentRecord } from '@/lib/api/consent';
import { CareEventExtractionConsentPanel } from './CareEventExtractionConsentPanel';

const consent: ConsentRecord = {
  consent_id: 'synthetic-care-consent', purpose_code: 'CARE_EVENT_EXTRACTION',
  consent_version: 2, status: 'GRANTED', policy_version: 'synthetic-policy',
  effective_at: '2026-09-22T00:00:00Z', expires_at: null, revoked_at: null,
  affected_capabilities: ['care_event_candidate'], deletion_request_id: null,
};
function success(data: unknown) {
  return new Response(JSON.stringify({ data, meta: {
    correlation_id: 'synthetic-correlation', timestamp: '2026-09-22T00:00:00Z', schema_version: '1.0',
  } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}
function setup(initialConsent: ConsentRecord | null = null, policyVersion = 'synthetic-policy') {
  const onChange = vi.fn();
  render(createElement(LocaleProvider, { initialLocale: 'zh-Hant', children:
    createElement(CareEventExtractionConsentPanel, {
      apiConfig: { apiBaseUrl: '/backend/core/' }, elderId: 'synthetic-elder',
      policyVersion, initialConsent, onChange,
    }),
  }));
  return onChange;
}
function fetchStub() {
  const mock = vi.fn<[RequestInfo | URL, RequestInit?], Promise<Response>>();
  vi.stubGlobal('fetch', mock);
  vi.stubGlobal('crypto', { randomUUID: () => 'synthetic-idempotency-key' });
  return mock;
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('elder care event consent', () => {
  it('does not infer extraction from other purposes or inactive extraction consent', () => {
    expect(activeCareEventExtractionConsent([
      { ...consent, purpose_code: 'BASIC_VOICE' },
      { ...consent, purpose_code: 'LONG_TERM_MEMORY' },
      { ...consent, purpose_code: 'FAMILY_SHARING' },
      { ...consent, status: 'REVOKED' },
      { ...consent, status: 'EXPIRED' },
    ])).toBeNull();
  });

  it('requires confirmation and grants only extraction before changing the displayed status', async () => {
    const fetch = fetchStub().mockResolvedValue(success({ items: [consent] }));
    const onChange = setup();
    fireEvent.click(screen.getByRole('button', { name: '開啟照護事件整理' }));
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '取消' }));
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '開啟照護事件整理' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '開啟照護事件整理' }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(consent));
    expect(screen.getByText('已開啟')).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, request] = fetch.mock.calls[0];
    expect(url).toBe('/backend/core/api/v1/elders/synthetic-elder/consents');
    expect(JSON.parse(String(request?.body))).toEqual({
      purposes: ['CARE_EVENT_EXTRACTION'], share_scopes: [], actor_confirmation: true,
      policy_version: 'synthetic-policy',
    });
    expect(new Headers(request?.headers).get('Idempotency-Key')).toContain('consent-care_event_extraction-');
    expect(new Headers(request?.headers).has('Authorization')).toBe(false);
  });

  it('revokes only the selected consent without requesting data deletion', async () => {
    const fetch = fetchStub().mockResolvedValue(success({ ...consent, status: 'REVOKED' }));
    const onChange = setup(consent);
    fireEvent.click(screen.getByRole('button', { name: '停止照護事件整理' }));
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '停止照護事件整理' }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(null));
    expect(screen.getByText('未開啟')).toBeTruthy();
    const [url, request] = fetch.mock.calls[0];
    expect(url).toBe('/backend/core/api/v1/elders/synthetic-elder/consents/synthetic-care-consent/revoke');
    expect(JSON.parse(String(request?.body))).toEqual({
      reason_code: 'ELDER_REQUESTED_CARE_EVENT_EXTRACTION_STOP', revoke_scope: [], request_deletion: false,
    });
  });

  it.each([null, consent])('keeps the prior choice after a rejected write (%s)', async (initial) => {
    const fetch = fetchStub().mockResolvedValue(new Response(JSON.stringify({ error: {
      code: 'conflict', message: 'private server detail', correlation_id: 'synthetic-correlation',
      details: null, reason_code: 'CONFLICT', retryable: false,
    } }), { status: 409, headers: { 'Content-Type': 'application/json' } }));
    const onChange = setup(initial);
    const label = initial ? '停止照護事件整理' : '開啟照護事件整理';
    fireEvent.click(screen.getByRole('button', { name: label }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: label }));
    await screen.findByRole('alert');
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText(initial ? '已開啟' : '未開啟')).toBeTruthy();
    expect(screen.queryByText('private server detail')).toBeNull();
  });

  it('rejects a grant response missing the requested purpose', async () => {
    fetchStub().mockResolvedValue(success({ items: [{ ...consent, purpose_code: 'BASIC_VOICE' }] }));
    const onChange = setup();
    fireEvent.click(screen.getByRole('button', { name: '開啟照護事件整理' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '開啟照護事件整理' }));
    await screen.findByRole('alert');
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText('未開啟')).toBeTruthy();
  });

  it('cannot grant without a configured policy version', () => {
    const fetch = fetchStub();
    setup(null, '');
    const trigger = screen.getByRole('button', { name: '開啟照護事件整理' }) as HTMLButtonElement;
    expect(trigger.disabled).toBe(true);
    fireEvent.click(trigger);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });
});
