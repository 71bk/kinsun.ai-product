// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AdminEntryLink } from './AdminEntryLink';
import { SurfaceShell } from './SurfaceShell';
import { LocaleProvider } from '@/lib/i18n/locale-context';

function profileResponse(role: string): Response {
  return new Response(
    JSON.stringify({
      data: { role, display_name: 'Synthetic Admin', tenant_id: 'synthetic-tenant', care_unit_ids: [] },
      meta: {
        correlation_id: 'synthetic-correlation',
        timestamp: '2026-09-18T00:00:00Z',
        schema_version: '1.0',
      },
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );
}

function mount(fetchImpl: () => Promise<Response>) {
  vi.stubGlobal(
    'fetch',
    vi.fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>().mockImplementation(fetchImpl),
  );
  return render(
    createElement(
      LocaleProvider,
      { initialLocale: 'en' as const, children: createElement(AdminEntryLink) },
    ),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('administrator console entry', () => {
  it('offers the console to an ADMIN actor', async () => {
    mount(() => Promise.resolve(profileResponse('ADMIN')));

    const link = await screen.findByRole('link', { name: /Admin console/ });
    expect(link.getAttribute('href')).toBe('/admin');
  });

  it.each(['DAYCARE_CARE_WORKER', 'HOME_CARE_WORKER', 'FAMILY_MEMBER', 'ELDER'])(
    'shows a %s no door that would 404 on them',
    async (role) => {
      const { container } = mount(() => Promise.resolve(profileResponse(role)));

      await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
      expect(container.textContent).toBe('');
    },
  );

  /* A failed profile read must not invent an entry, and must not take the
     surrounding chrome down with it — the page's own data load is what reports
     a broken session. */
  it('stays silent when the profile cannot be read', async () => {
    const { container } = mount(() => Promise.reject(new TypeError('Failed to fetch')));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container.textContent).toBe('');
  });

  it('asks Core for the actor and nothing else', async () => {
    mount(() => Promise.resolve(profileResponse('ADMIN')));

    await screen.findByRole('link', { name: /Admin console/ });
    const calls = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
    expect(calls).toHaveLength(1);
    expect(String(calls[0]?.[0])).toBe('/backend/core/api/v1/me');
  });
});

describe('shell chrome by surface', () => {
  function markup(surface: 'care' | 'family' | 'admin') {
    return renderToStaticMarkup(
      createElement(SurfaceShell, {
        surface,
        initialLocale: 'en' as const,
        signedIn: true,
        children: createElement('main', null, 'Synthetic content'),
      }),
    );
  }

  it('makes the admin label the way back to the ledger', () => {
    expect(markup('admin')).toContain('href="/admin"');
  });

  it.each(['care', 'family'] as const)('leaves the %s label inert', (surface) => {
    expect(markup(surface)).not.toContain('href="/admin"');
  });

  /* A family member cannot hold the ADMIN role, so the family surface must not
     spend a `/api/v1/me` round trip on every page to find that out. */
  it('never mounts the console entry on the family surface', () => {
    const fetchMock = vi.fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>();
    vi.stubGlobal('fetch', fetchMock);

    markup('family');

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
