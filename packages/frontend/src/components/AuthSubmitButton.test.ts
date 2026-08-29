import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AuthSubmitButton } from './AuthSubmitButton';

describe('AuthSubmitButton pending state', () => {
  it('disables repeat submission and exposes an accessible progress state', () => {
    const markup = renderToStaticMarkup(
      createElement(AuthSubmitButton, {
        children: '登入',
        pending: true,
        pendingLabel: '登入中…',
      }),
    );

    expect(markup).toContain('disabled=""');
    expect(markup).toContain('aria-busy="true"');
    expect(markup).toContain('aria-live="polite"');
    expect(markup).toContain('登入中…');
    expect(markup).not.toContain('>登入</button>');
  });

  it('can be disabled without replacing its label with pending text', () => {
    const markup = renderToStaticMarkup(
      createElement(AuthSubmitButton, {
        children: '使用 LINE 登入',
        disabled: true,
        pendingLabel: '登入中…',
      }),
    );

    expect(markup).toContain('disabled=""');
    expect(markup).toContain('aria-busy="false"');
    expect(markup).toContain('使用 LINE 登入');
    expect(markup).not.toContain('登入中…');
  });
});
