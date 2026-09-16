// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import type { EventCorrection, EventView } from '@/lib/api/events';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { EventReviewControls } from './EventReviewControls';

/* US-B03: a CORRECT review can change the event's content, type and time.
   The controls turn what the reviewer did into the client's omit / set /
   clear correction, and only a CORRECT decision carries one at all. */

function event(overrides: Partial<EventView> = {}): EventView {
  return {
    eventId: 'synthetic-event',
    elderId: 'synthetic-elder',
    eventType: 'MEAL',
    eventDate: '2026-08-13',
    eventTime: '2026-08-13T08:00:00Z',
    content: 'Synthetic breakfast',
    status: 'NEEDS_REVIEW',
    confidenceBand: 'LOW',
    evidenceRefs: ['utterance-1'],
    version: 1,
    consentVersion: 1,
    structuredPayload: { summary: 'Synthetic breakfast' },
    ...overrides,
  };
}

function mount(view: EventView) {
  const onReview = vi.fn(async () => undefined);
  render(
    createElement(LocaleProvider, {
      initialLocale: 'en',
      children: createElement(EventReviewControls, { event: view, onReview }),
    }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Review' }));
  return onReview;
}

function chooseCorrect() {
  fireEvent.change(screen.getByLabelText('Review decision'), { target: { value: 'CORRECT' } });
}

async function submit() {
  fireEvent.click(screen.getByRole('button', { name: 'Submit review' }));
  // The dialog confirms through its form's submit handler.
  const form = document.querySelector('dialog form') as HTMLFormElement;
  fireEvent.submit(form);
  await screen.findByRole('button', { name: 'Review' });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it('shows type and time fields only for a CORRECT decision, prefilled from the event', () => {
  mount(event());
  expect(screen.queryByLabelText('Corrected event type')).toBeNull();
  chooseCorrect();
  const type = screen.getByLabelText('Corrected event type') as HTMLSelectElement;
  const time = screen.getByLabelText('Corrected event time') as HTMLInputElement;
  expect(type.value).toBe('MEAL');
  expect(time.type).toBe('datetime-local');
  // prefilled from the event's own time, expressed in the browser's local zone
  const expected = new Date('2026-08-13T08:00:00Z');
  const local = new Date(expected.getTime() - expected.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
  expect(time.value).toBe(local);
});

it('leaves an untouched type and time undefined so the client omits them', async () => {
  const onReview = mount(event());
  chooseCorrect();
  fireEvent.change(screen.getByLabelText('Corrected content'), { target: { value: 'Ate congee' } });
  await submit();
  const [, decision, correction] = onReview.mock.calls[0] as [EventView, string, EventCorrection];
  expect(decision).toBe('CORRECT');
  expect(correction.content).toBe('Ate congee');
  expect(correction.eventType).toBe('MEAL');
  expect(correction.eventTime).toBeUndefined();
});

it('sends a changed type and a new time as a timezone-qualified timestamp', async () => {
  const onReview = mount(event());
  chooseCorrect();
  fireEvent.change(screen.getByLabelText('Corrected event type'), { target: { value: 'SLEEP' } });
  fireEvent.change(screen.getByLabelText('Corrected event time'), {
    target: { value: '2026-08-13T21:30' },
  });
  await submit();
  const correction = onReview.mock.calls[0][2] as EventCorrection;
  expect(correction.eventType).toBe('SLEEP');
  expect(correction.eventTime).toBe(new Date('2026-08-13T21:30').toISOString());
  expect(correction.eventTime).toMatch(/Z$/);
});

it('sends null to clear a recorded time, and nothing when there was no time to clear', async () => {
  const onReview = mount(event());
  chooseCorrect();
  fireEvent.click(screen.getByLabelText('This event has no recorded time'));
  expect((screen.getByLabelText('Corrected event time') as HTMLInputElement).disabled).toBe(true);
  await submit();
  expect((onReview.mock.calls[0][2] as EventCorrection).eventTime).toBeNull();

  cleanup();
  const second = mount(event({ eventTime: null }));
  chooseCorrect();
  fireEvent.click(screen.getByLabelText('This event has no recorded time'));
  await submit();
  expect((second.mock.calls[0][2] as EventCorrection).eventTime).toBeUndefined();
});

it('passes no correction for VERIFY', async () => {
  const onReview = mount(event());
  await submit();
  expect(onReview.mock.calls[0][1]).toBe('VERIFY');
  expect(onReview.mock.calls[0][2]).toBeUndefined();
});
