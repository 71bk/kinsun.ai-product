import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  cookieGet: vi.fn(),
  clearBrowserStateRender: vi.fn(),
}));

vi.mock('next/headers', () => ({
  cookies: async () => ({ get: mocks.cookieGet }),
}));

vi.mock('@/components/ClearBrowserSessionState', () => ({
  ClearBrowserSessionState: () => {
    mocks.clearBrowserStateRender();
    return null;
  },
}));

import SignInPage from './page';

beforeEach(() => {
  mocks.cookieGet.mockReset();
  mocks.clearBrowserStateRender.mockReset();
});

describe('sign-in browser-state cleanup guard', () => {
  it.each(['zh-Hant', 'en'])('describes email/password login in %s without requiring Google', async (locale) => {
    mocks.cookieGet.mockImplementation((name: string) =>
      name === 'kinsun_ui_locale' ? { value: locale } : undefined,
    );
    const markup = renderToStaticMarkup(await SignInPage({ searchParams: Promise.resolve({ error: 'login' }) }));
    expect(markup).toContain(locale === 'en' ? 'email and password' : 'Email 與密碼');
    expect(markup).not.toContain('Google');
    expect(markup).toContain('role="alert"');
    expect(markup).toContain('/staff/sign-in');
    expect(markup).toContain('/family/join');
    expect(markup).toContain('/elder/start');
  });
  it('preserves browser state while an App Session cookie remains', async () => {
    mocks.cookieGet.mockImplementation((name: string) =>
      name === 'kinsun_session' ? { value: `ks1_${'a'.repeat(43)}` } : undefined,
    );

    const page = await SignInPage({ searchParams: Promise.resolve({}) });
    renderToStaticMarkup(page);

    expect(mocks.cookieGet).toHaveBeenCalledWith('kinsun_session');
    expect(mocks.clearBrowserStateRender).not.toHaveBeenCalled();
  });

  it('clears stale browser state when no authentication cookie remains', async () => {
    mocks.cookieGet.mockReturnValue(undefined);

    const page = await SignInPage({ searchParams: Promise.resolve({}) });
    renderToStaticMarkup(page);

    expect(mocks.clearBrowserStateRender).toHaveBeenCalledTimes(1);
  });
});
