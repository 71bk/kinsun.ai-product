// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RootError from './error';
import NotFound from './not-found';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/* These render inside the root layout, which has no LocaleProvider — the voice
   surface is Chinese-only (MASTER.md §5.2). The point of these tests is that
   they render at all: an earlier draft reached for the shared ErrorState, whose
   useLocale() throws outside a provider, which would have made the error page
   the thing that crashes. */
describe('root not-found', () => {
  it('renders without a LocaleProvider', () => {
    expect(() => render(createElement(NotFound))).not.toThrow();
  });

  it('offers a way back rather than a dead end', () => {
    render(createElement(NotFound));

    expect(screen.getByRole('link', { name: '回到首頁' }).getAttribute('href')).toBe('/');
  });

  /* MASTER.md §1: the subject of a failure message is the system, and 錯誤 /
     失敗 / 無效 are not used on a surface a 75+ reader may be looking at. */
  it('does not blame the reader', () => {
    const { container } = render(createElement(NotFound));

    expect(container.textContent).not.toMatch(/錯誤|失敗|無效/);
  });
});

describe('root error boundary', () => {
  it('renders without a LocaleProvider', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    expect(() =>
      render(createElement(RootError, { error: new Error('synthetic'), reset: () => undefined })),
    ).not.toThrow();
  });

  it('announces the failure, offers retry and a way home', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const reset = vi.fn();

    render(createElement(RootError, { error: new Error('synthetic'), reset }));

    expect(screen.getByRole('alert')).toBeTruthy();
    expect(screen.getByRole('link', { name: '回到首頁' }).getAttribute('href')).toBe('/');
    screen.getByRole('button', { name: /再試一次/ }).click();
    expect(reset).toHaveBeenCalledOnce();
  });

  it('never renders the error message', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { container } = render(
      createElement(RootError, {
        error: new Error('elder transcript 我今天很難過'),
        reset: () => undefined,
      }),
    );

    expect(container.textContent).not.toContain('很難過');
    expect(container.textContent).not.toContain('transcript');
  });

  it('does not blame the reader', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { container } = render(
      createElement(RootError, { error: new Error('synthetic'), reset: () => undefined }),
    );

    expect(container.textContent).not.toMatch(/錯誤|失敗|無效/);
  });

  it('logs the name and digest but never the message', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const error = Object.assign(new Error('restricted detail'), { digest: 'def456' });

    render(createElement(RootError, { error, reset: () => undefined }));

    const logged = JSON.stringify(spy.mock.calls);
    expect(logged).toContain('def456');
    expect(logged).not.toContain('restricted detail');
  });
});
