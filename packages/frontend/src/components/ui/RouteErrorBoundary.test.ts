// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { createElement, type ReactElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FamilyDataRedlineError } from '@/lib/api/family-guard';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { RouteErrorBoundary } from './RouteErrorBoundary';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function withLocale(element: ReactElement, locale: 'zh-Hant' | 'en') {
  return createElement(LocaleProvider, { initialLocale: locale, children: element });
}

/** jsdom so the boundary's useEffect actually runs — the logging is behaviour. */
function renderBoundary(error: Error, locale: 'zh-Hant' | 'en' = 'en'): string {
  const { container } = render(
    withLocale(
      createElement(RouteErrorBoundary, { error, reset: () => undefined, scope: 'family' }),
      locale,
    ),
  );
  return container.innerHTML;
}

describe('RouteErrorBoundary', () => {
  /* The reason this boundary exists at all. MASTER.md §11: a report withheld by
     the redline must leave no trace on screen, and the error's own message
     names the restricted field Core sent. */
  it('renders nothing from a redline error, including the field name', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const markup = renderBoundary(new FamilyDataRedlineError('transcript'));

    expect(markup).not.toContain('transcript');
    expect(markup).not.toContain('FamilyDataRedlineError');
    expect(markup).not.toContain('must never receive');
  });

  it('withholds the message of an arbitrary error too', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const markup = renderBoundary(new Error('elder said 我今天很難過 at 09:14'));

    expect(markup).not.toContain('很難過');
    expect(markup).not.toContain('09:14');
  });

  it('announces the failure and offers a way forward', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    renderBoundary(new Error('synthetic'));

    expect(screen.getByRole('alert')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
    expect(screen.getByText(/This page cannot be shown right now/)).toBeTruthy();
  });

  it('translates the boundary copy', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const markup = renderBoundary(new Error('synthetic'), 'zh-Hant');

    expect(markup).toContain('目前沒辦法顯示這一頁的內容');
  });

  it('calls reset when the retry button is pressed', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const reset = vi.fn();

    render(
      withLocale(
        createElement(RouteErrorBoundary, { error: new Error('synthetic'), reset, scope: 'family' }),
        'en',
      ),
    );
    screen.getByRole('button', { name: 'Retry' }).click();

    expect(reset).toHaveBeenCalledOnce();
  });

  /* The message is the thing the boundary just refused to put on screen, so it
     must not reach a log either (AGENTS.md §4). */
  it('logs the name and digest but never the message', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const error = Object.assign(new Error('restricted detail'), { digest: 'abc123' });

    renderBoundary(error);

    expect(spy).toHaveBeenCalled();
    const logged = JSON.stringify(spy.mock.calls);
    expect(logged).toContain('abc123');
    expect(logged).toContain('family');
    expect(logged).not.toContain('restricted detail');
  });
});
