// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, expect, it } from 'vitest';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { ElderCard } from './ElderCard';

afterEach(cleanup);

it.each([
  ['zh-Hant', 0, '未結案待辦：0 筆'],
  ['zh-Hant', 105, '未結案待辦：105 筆'],
  ['en', 3, 'Unfinished care actions: 3'],
] as const)('renders exact count in %s', (locale, count, label) => {
  render(createElement(LocaleProvider, { initialLocale: locale, children:
    createElement(ElderCard, { elder: {
      elderId: 'synthetic', elderName: 'Synthetic Elder', careUnitName: null,
      authorizationSummary: null, openCareActionCount: count, pendingEventReviewCount: null,
    } }),
  }));
  expect(screen.getByText(label)).toBeDefined();
  expect(screen.getByRole('link').getAttribute('href')).toBe('/staff/elders/synthetic');
});

it('hides unavailable count instead of claiming zero', () => {
  render(createElement(LocaleProvider, { initialLocale: 'en', children:
    createElement(ElderCard, { elder: {
      elderId: 'synthetic', elderName: 'Synthetic Elder', careUnitName: null,
      authorizationSummary: null, openCareActionCount: null, pendingEventReviewCount: null,
    } }),
  }));
  expect(screen.queryByText(/Unfinished care actions/)).toBeNull();
  expect(screen.queryByText(/Pending events/)).toBeNull();
});

it.each([
  ['zh-Hant', 0, '待覆核事件：0 筆・前往覆核'],
  ['zh-Hant', 105, '待覆核事件：105 筆・前往覆核'],
  ['en', 3, 'Pending events: 3 · Review'],
] as const)('links %s pending counts to the filtered queue', (locale, count, label) => {
  render(createElement(LocaleProvider, { initialLocale: locale, children:
    createElement(ElderCard, { elder: {
      elderId: 'synthetic', elderName: 'Synthetic Elder', careUnitName: null,
      authorizationSummary: null, openCareActionCount: null, pendingEventReviewCount: count,
    } }),
  }));
  expect(screen.getByRole('link', { name: label }).getAttribute('href')).toBe('/staff/elders/synthetic?review=pending');
});
