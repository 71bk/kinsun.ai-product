import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createElement, type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import type { FamilyReportView } from '@/lib/api/family-reports';
import { FamilySummaryCard } from './FamilySummaryCard';
import { ReportCard } from './ReportCard';

function source(relativeUrl: string): string {
  return readFileSync(fileURLToPath(new URL(relativeUrl, import.meta.url)), 'utf8');
}

function renderWithLocale(element: ReactElement, locale: 'zh-Hant' | 'en' = 'en'): string {
  return renderToStaticMarkup(
    createElement(LocaleProvider, { initialLocale: locale, children: element }),
  );
}

function report(overrides: Partial<FamilyReportView> = {}): FamilyReportView {
  return {
    reportId: 'synthetic-report',
    elderId: 'synthetic-elder',
    reportType: 'DAILY',
    periodStart: '2026-08-13',
    periodEnd: '2026-08-13',
    status: 'PUBLISHED',
    items: [
      {
        category: 'MEAL',
        text: 'Synthetic published item that must not leak in a withdrawn card',
        sourceIds: ['opaque-reference-must-not-render'],
      },
    ],
    dataGapNotice: null,
    version: 2,
    publishedAt: '2026-08-13T09:00:00Z',
    withdrawnAt: null,
    updatedAt: '2026-08-13T09:00:00Z',
    ...overrides,
  };
}

describe('Family Surface safety semantics', () => {
  it('offers only the two authenticated family destinations', () => {
    const nav = source('./FamilyNav.tsx');

    expect(nav).toContain("href: '/family'");
    expect(nav).toContain("href: '/family/reports'");
    expect(nav).not.toMatch(/href:\s*['"]\/(admin|family\/settings|dashboard)/i);
  });

  /* §10.3: a withdrawn report keeps no items, not even collapsed — the same
     source data that renders normally when PUBLISHED must vanish entirely
     once the status flips to WITHDRAWN. */
  it('renders no items for a withdrawn report even though the data still has them', () => {
    const markup = renderWithLocale(
      createElement(ReportCard, { report: report({ status: 'WITHDRAWN' }) }),
    );

    expect(markup).not.toContain('Synthetic published item');
    expect(markup).toMatch(/withdrawn/i);
  });

  it('shows a first-class Data Insufficient shape instead of an empty published card', () => {
    const markup = renderWithLocale(createElement(ReportCard, { report: report({ items: [] }) }));

    expect(markup).not.toContain('<ul');
    expect(markup).toMatch(/data-state="dataInsufficient"/);
  });

  it('states an evidence count without exposing the opaque source reference itself', () => {
    const markup = renderWithLocale(createElement(ReportCard, { report: report() }));

    expect(markup).not.toContain('opaque-reference-must-not-render');
    expect(markup).not.toMatch(/transcript|utterance/i);
  });

  it('links to the detail route only when asked to, so the detail page does not link to itself', () => {
    const withLink = renderWithLocale(createElement(ReportCard, { report: report() }));
    const withoutLink = renderWithLocale(
      createElement(ReportCard, { linkToDetail: false, report: report() }),
    );

    expect(withLink).toContain('/family/reports/synthetic-report');
    expect(withoutLink).not.toContain('href=');
  });

  it('gives the three home-page sections one consistent titled card shape', () => {
    const markup = renderWithLocale(
      createElement(FamilySummaryCard, { title: 'This week', children: 'Synthetic body' }),
    );

    expect(markup).toContain('<h2');
    expect(markup).toContain('This week');
    expect(markup).toContain('Synthetic body');
  });

  /* Stitch plan §5: "整體狀況穩定" / mood or anomaly inference must never reach
     the family surface — only Core-published record counts and gaps may. */
  it('keeps the home page free of health, mood or anomaly conclusions', () => {
    const home = source('../../app/family/(app)/page.tsx');

    expect(home).not.toMatch(/穩定|情緒指標|異常活動|risk score|stable|anomaly/i);
  });

  it('keeps SOS/ambulance escalation out of the family surface entirely', () => {
    const home = source('../../app/family/(app)/page.tsx');
    const reports = source('../../app/family/(app)/reports/page.tsx');
    const detail = source('../../app/family/(app)/reports/[reportId]/page.tsx');

    for (const file of [home, reports, detail]) {
      // Word-boundary on SOS: a bare /SOS/i also matches inside `toISOString`.
      expect(file).not.toMatch(/ambulance|救護車|\bSOS\b/i);
    }
  });
});

describe('Family Surface styling boundary', () => {
  it.each([
    'FamilyNav.module.css',
    'FamilySummaryCard.module.css',
    'ReportCard.module.css',
    '../../app/family/(app)/FamilyHomePage.module.css',
    '../../app/family/(app)/reports/FamilyReportsPage.module.css',
    '../../app/family/(app)/reports/[reportId]/ReportDetailPage.module.css',
  ])('%s contains no raw hex colours', (relativePath) => {
    const css = source(relativePath);
    expect(css).not.toMatch(/#(?:[0-9a-fA-F]{3,4}){1,2}\b/);
  });

  it('does not fall back to horizontal page scrolling for narrow viewports', () => {
    for (const path of [
      'FamilyNav.module.css',
      '../../app/family/(app)/FamilyHomePage.module.css',
      '../../app/family/(app)/reports/FamilyReportsPage.module.css',
    ]) {
      expect(source(path)).not.toMatch(/overflow-x:\s*(auto|scroll)/);
    }
  });
});
