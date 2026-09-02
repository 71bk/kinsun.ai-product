// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createElement, Fragment, useState } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { LocaleProvider } from '@/lib/i18n/locale-context';
import { ConfirmationDialog } from './ConfirmationDialog';

afterEach(() => cleanup());

function Harness() {
  const [open, setOpen] = useState(false);
  return createElement(
    LocaleProvider,
    { initialLocale: 'en' },
    createElement(
      Fragment,
      null,
      createElement(
        'button',
        { onClick: () => setOpen(true), type: 'button' },
        'Open confirmation',
      ),
      createElement(ConfirmationDialog, {
        description: 'The formal record will be version checked.',
        onCancel: () => setOpen(false),
        onConfirm: () => setOpen(false),
        open,
        title: 'Start work?',
      }),
    ),
  );
}

describe('ConfirmationDialog focus lifecycle', () => {
  it('returns focus to the invoking control after cancellation', () => {
    render(createElement(Harness));
    const trigger = screen.getByRole('button', { name: 'Open confirmation' });
    trigger.focus();
    fireEvent.click(trigger);

    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cancel' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(document.activeElement).toBe(trigger);
  });
});
