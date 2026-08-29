// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { ElderAuthView } from './ElderAuthView';

afterEach(() => {
  cleanup();
});

function renderAuth(overrides: Partial<Parameters<typeof ElderAuthView>[0]> = {}) {
  render(
    createElement(ElderAuthView, {
      nativeEnabled: true,
      showGoogle: false,
      showLine: false,
      ...overrides,
    }),
  );
}

describe('ElderAuthView tabs', () => {
  it('starts on login and switches to the registration form without mixing both flows', () => {
    renderAuth();

    const loginTab = screen.getByRole('tab', { name: '登入' });
    const registerTab = screen.getByRole('tab', { name: '註冊' });
    expect(loginTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByLabelText('密碼')).toBeTruthy();
    expect(screen.queryByLabelText('希望我們怎麼稱呼您')).toBeNull();

    fireEvent.click(registerTab);

    expect(registerTab.getAttribute('aria-selected')).toBe('true');
    expect(loginTab.getAttribute('aria-selected')).toBe('false');
    expect(screen.getByLabelText('希望我們怎麼稱呼您')).toBeTruthy();
    expect(screen.queryByLabelText('密碼')).toBeNull();
  });

  it('supports arrow-key tab navigation', () => {
    renderAuth();

    const loginTab = screen.getByRole('tab', { name: '登入' });
    fireEvent.keyDown(loginTab, { key: 'ArrowRight' });

    const registerTab = screen.getByRole('tab', { name: '註冊' });
    expect(registerTab.getAttribute('aria-selected')).toBe('true');
    expect(document.activeElement).toBe(registerTab);
  });

  it('keeps linked providers in the login tab only', () => {
    renderAuth({ showGoogle: true, showLine: true });

    expect(screen.getByRole('button', { name: '使用 Google 登入' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '使用 LINE 登入' })).toBeTruthy();

    fireEvent.click(screen.getByRole('tab', { name: '註冊' }));

    expect(screen.queryByRole('button', { name: '使用 Google 登入' })).toBeNull();
    expect(screen.queryByRole('button', { name: '使用 LINE 登入' })).toBeNull();
  });
});
