import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createElement, type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import type { AssignmentView } from '@/lib/api/assignments';
import type { EventView } from '@/lib/api/events';
import { AssignmentCard } from './AssignmentCard';
import { EvidenceBlock } from './EvidenceBlock';
import { ReviewCard } from './ReviewCard';

function renderWithLocale(element: ReactElement): string {
  return renderToStaticMarkup(
    createElement(LocaleProvider, { initialLocale: 'en', children: element }),
  );
}

function event(status: EventView['status']): EventView {
  return {
    eventId: 'synthetic-event',
    elderId: 'synthetic-elder',
    eventType: 'MEAL',
    eventDate: '2026-08-13',
    content: 'Synthetic source-backed event',
    status,
    confidenceBand: 'LOW',
    evidenceRefs: ['opaque-reference-must-not-render'],
    version: 2,
    consentVersion: 1,
    structuredPayload: { summary: 'Synthetic source-backed event' },
  };
}

function assignment(status: AssignmentView['status']): AssignmentView {
  return {
    assignmentId: 'synthetic-assignment',
    elderId: 'synthetic-elder',
    scheduledStart: '2026-08-13T01:00:00Z',
    scheduledEnd: '2026-08-13T02:00:00Z',
    status,
    scopeCount: 2,
    version: 3,
    expiresAt: '2026-08-13T02:00:00Z',
  };
}

describe('Care Surface safety semantics', () => {
  it('renders evidence count and versions without exposing opaque references or transcripts', () => {
    const evidenceMarkup = renderWithLocale(
      createElement(EvidenceBlock, { sourceCount: 1, version: 2, consentVersion: 1 }),
    );
    const cardMarkup = renderWithLocale(
      createElement(ReviewCard, { event: event('VERIFIED'), onReview: async () => undefined }),
    );

    expect(evidenceMarkup).toContain('Source count');
    expect(evidenceMarkup).toContain('Consent version');
    expect(cardMarkup).not.toContain('opaque-reference-must-not-render');
    expect(cardMarkup).not.toMatch(/transcript|utterance/i);
  });

  it('offers review only while the event is unsettled', () => {
    const candidate = renderWithLocale(
      createElement(ReviewCard, { event: event('NEEDS_REVIEW'), onReview: async () => undefined }),
    );
    const verified = renderWithLocale(
      createElement(ReviewCard, { event: event('VERIFIED'), onReview: async () => undefined }),
    );

    expect(candidate).toContain('Review');
    expect(verified).not.toContain('Review');
    expect(verified).toContain('Verified');
  });

  it('offers only contract-supported assignment transitions', () => {
    const confirmed = renderWithLocale(
      createElement(AssignmentCard, {
        assignment: assignment('CONFIRMED'),
        onCommand: async () => undefined,
      }),
    );
    const completed = renderWithLocale(
      createElement(AssignmentCard, {
        assignment: assignment('COMPLETED'),
        onCommand: async () => undefined,
      }),
    );

    expect(confirmed).toContain('Start service');
    expect(confirmed).not.toContain('Complete service');
    expect(completed).not.toContain('Start service');
    expect(completed).not.toContain('Complete service');
  });

  it('does not introduce health scoring or treatment actions into care cards', () => {
    const markup = renderWithLocale(
      createElement(AssignmentCard, {
        assignment: assignment('CONFIRMED'),
        onCommand: async () => undefined,
      }),
    );
    expect(markup).not.toMatch(/health score|risk score|diagnos|medication advice/i);
  });
});

describe('Care Surface styling boundary', () => {
  it.each([
    'AssignmentCard.module.css',
    'CareSidebar.module.css',
    'ElderCard.module.css',
    'EventReviewControls.module.css',
    'EvidenceBlock.module.css',
    'ReviewCard.module.css',
    '../dashboard/ElderOverviewList.module.css',
    '../dashboard/EventFilterBar.module.css',
    '../dashboard/EventTable.module.css',
    '../dashboard/MemoryList.module.css',
  ])('%s contains no raw hex colours', (relativePath) => {
    const css = readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8');
    expect(css).not.toMatch(/#(?:[0-9a-fA-F]{3,4}){1,2}\b/);
  });

  it('switches the event table to cards instead of horizontal page scrolling', () => {
    const css = readFileSync(
      fileURLToPath(new URL('../dashboard/EventTable.module.css', import.meta.url)),
      'utf8',
    );
    expect(css).toMatch(/@container\s*\(max-width:\s*60rem\)/);
    expect(css).not.toMatch(/overflow-x:\s*(auto|scroll)/);
  });
});
