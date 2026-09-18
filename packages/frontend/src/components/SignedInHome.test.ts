// @vitest-environment jsdom

import { cleanup, render, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { destinationFor, ELDER_HOME } from '@/lib/role-destination';

const replace = vi.fn<[string], void>();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

/* The companion pulls in the voice stack, a service worker registration and a
   WebSocket panel; none of that is what this component decides. Standing in for
   it keeps the test about the routing and lets it run in jsdom. */
vi.mock('@/components/voice/VoiceHomeClient', () => ({
  VoiceHomeClient: () => createElement('main', null, 'Synthetic companion'),
}));

const { SignedInHome } = await import('./SignedInHome');

function profileResponse(role: string): Response {
  return new Response(
    JSON.stringify({
      data: { role, display_name: 'Synthetic Actor', tenant_id: 't', care_unit_ids: [] },
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
  return render(createElement(SignedInHome));
}

afterEach(() => {
  cleanup();
  replace.mockReset();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('role table', () => {
  it.each([
    ['ELDER', '/'],
    ['FAMILY_MEMBER', '/family'],
    ['DAYCARE_CARE_WORKER', '/staff'],
    ['HOME_CARE_WORKER', '/staff'],
    ['ADMIN', '/admin'],
  ])('sends %s to %s', (role, expected) => {
    expect(destinationFor({ role })).toBe(expected);
  });

  it('reads the older actor_type shape when role is absent', () => {
    expect(destinationFor({ actor_type: 'ADMIN' })).toBe('/admin');
  });

  it('refuses to invent a surface for an unknown role', () => {
    expect(destinationFor({ role: 'CONTENT_MANAGER' })).toBeNull();
    expect(destinationFor({})).toBeNull();
  });
});

describe('signed-in home', () => {
  it('renders the companion without waiting for the role', () => {
    // Never settles: the elder must not be gated behind this lookup.
    const { container } = mount(() => new Promise<Response>(() => undefined));

    expect(container.textContent).toContain('Synthetic companion');
    expect(replace).not.toHaveBeenCalled();
  });

  it('leaves an elder on their own home screen', async () => {
    mount(() => Promise.resolve(profileResponse('ELDER')));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(replace).not.toHaveBeenCalled();
    expect(destinationFor({ role: 'ELDER' })).toBe(ELDER_HOME);
  });

  it.each([
    ['FAMILY_MEMBER', '/family'],
    ['DAYCARE_CARE_WORKER', '/staff'],
    ['HOME_CARE_WORKER', '/staff'],
    ['ADMIN', '/admin'],
  ])('moves %s off the voice surface to %s', async (role, expected) => {
    mount(() => Promise.resolve(profileResponse(role)));

    await waitFor(() => expect(replace).toHaveBeenCalledWith(expected));
    expect(replace).toHaveBeenCalledTimes(1);
  });

  /* A role with no surface yet is left with the companion's own message rather
     than bounced somewhere equally unusable. */
  it('stays put for a role that has no surface', async () => {
    mount(() => Promise.resolve(profileResponse('CONTENT_MANAGER')));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(replace).not.toHaveBeenCalled();
  });

  it('stays put when the profile cannot be read', async () => {
    const { container } = mount(() => Promise.reject(new TypeError('Failed to fetch')));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(replace).not.toHaveBeenCalled();
    expect(container.textContent).toContain('Synthetic companion');
  });

  it('asks Core once, for the actor only', async () => {
    mount(() => Promise.resolve(profileResponse('ADMIN')));

    await waitFor(() => expect(replace).toHaveBeenCalled());
    const calls = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
    expect(calls).toHaveLength(1);
    expect(String(calls[0]?.[0])).toBe('/backend/core/api/v1/me');
  });
});
