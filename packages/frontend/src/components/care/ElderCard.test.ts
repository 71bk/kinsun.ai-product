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
      authorizationSummary: null, openCareActionCount: count,
    } }),
  }));
  expect(screen.getByText(label)).toBeDefined();
  expect(screen.getByRole('link').getAttribute('href')).toBe('/staff/elders/synthetic');
});

it('hides unavailable count instead of claiming zero', () => {
  render(createElement(LocaleProvider, { initialLocale: 'en', children:
    createElement(ElderCard, { elder: {
      elderId: 'synthetic', elderName: 'Synthetic Elder', careUnitName: null,
      authorizationSummary: null, openCareActionCount: null,
    } }),
  }));
  expect(screen.queryByText(/Unfinished care actions/)).toBeNull();
});
