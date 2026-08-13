import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createElement, type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { PageHeader } from '@/components/layout/PageHeader';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { ConfirmationDialog } from './ConfirmationDialog';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { FilterChip } from './FilterChip';
import { SearchField } from './SearchField';
import { SummaryMetricCard } from './SummaryMetricCard';

function renderWithLocale(element: ReactElement, locale: 'zh-Hant' | 'en' = 'en'): string {
  return renderToStaticMarkup(
    createElement(LocaleProvider, { initialLocale: locale, children: element }),
  );
}

describe('shared design foundation semantics', () => {
  it('gives every page one explicit h1 and keeps supporting copy separate', () => {
    const markup = renderToStaticMarkup(
      createElement(PageHeader, {
        title: 'Synthetic care page',
        description: 'Synthetic description',
        meta: 'Version 3',
      }),
    );

    expect(markup.match(/<h1/g)).toHaveLength(1);
    expect(markup).toContain('Synthetic description');
    expect(markup).toContain('Version 3');
  });

  it('renders a neutral metric as a description list', () => {
    const markup = renderToStaticMarkup(
      createElement(SummaryMetricCard, {
        label: 'Records awaiting review',
        value: 4,
        description: 'Workflow count only',
      }),
    );

    expect(markup).toContain('<dl');
    expect(markup).toContain('<dt');
    expect(markup).toContain('<dd');
    expect(markup).not.toMatch(/risk|score|healthy/i);
  });

  it('exposes filter selection to assistive technology', () => {
    const markup = renderToStaticMarkup(
      createElement(FilterChip, {
        selected: true,
        onClick: () => undefined,
        count: 3,
        children: 'Needs review',
      }),
    );

    expect(markup).toContain('aria-pressed="true"');
    expect(markup).toContain('Needs review');
    expect(markup).toContain('3');
  });

  it('keeps search labelled and gives the icon-only clear control a name', () => {
    const markup = renderWithLocale(
      createElement(SearchField, {
        value: 'synthetic',
        onChange: () => undefined,
      }),
    );

    expect(markup).toContain('type="search"');
    expect(markup).toContain('<label');
    expect(markup).toContain('aria-label="Clear search"');
  });

  it('distinguishes empty content from a system error', () => {
    const emptyMarkup = renderWithLocale(
      createElement(EmptyState, { description: 'No matching synthetic records' }),
    );
    const errorMarkup = renderWithLocale(
      createElement(ErrorState, { description: 'Synthetic request could not be completed' }),
    );

    expect(emptyMarkup).toContain('role="status"');
    expect(emptyMarkup).toContain('No data yet');
    expect(errorMarkup).toContain('role="alert"');
    expect(errorMarkup).toContain('Content is unavailable');
  });

  it('renders a named modal with separate cancel and destructive confirmation actions', () => {
    const markup = renderWithLocale(
      createElement(ConfirmationDialog, {
        open: true,
        title: 'Remove synthetic record?',
        description: 'This test does not invoke an API.',
        tone: 'destructive',
        onCancel: () => undefined,
        onConfirm: () => undefined,
      }),
    );

    expect(markup).toContain('<dialog');
    expect(markup).toContain('aria-modal="true"');
    expect(markup).toContain('Cancel');
    expect(markup).toContain('Confirm');
    expect(markup).toContain('data-tone="destructive"');
  });
});

describe('shared design foundation styling boundary', () => {
  it.each([
    'PageHeader.module.css',
    '../ui/SummaryMetricCard.module.css',
    '../ui/FilterChip.module.css',
    '../ui/SearchField.module.css',
    '../ui/EmptyState.module.css',
    '../ui/ErrorState.module.css',
    '../ui/ConfirmationDialog.module.css',
  ])('%s contains no raw hex colours', (relativePath) => {
    const css = readFileSync(
      fileURLToPath(new URL(`../layout/${relativePath}`, import.meta.url)),
      'utf8',
    );
    expect(css).not.toMatch(/#(?:[0-9a-fA-F]{3,4}){1,2}\b/);
  });

  it('does not split the language label at tablet widths', () => {
    const css = readFileSync(
      fileURLToPath(new URL('../LanguageSwitch.module.css', import.meta.url)),
      'utf8',
    );
    expect(css).toMatch(/\.label\s*\{[^}]*white-space:\s*nowrap/s);
  });
});
