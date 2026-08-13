import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SurfaceShell } from './SurfaceShell';

describe('SurfaceShell session affordance', () => {
  it('renders a real sign-out POST only when a session cookie is present', () => {
    const signedIn = renderToStaticMarkup(
      createElement(SurfaceShell, {
        surface: 'family',
        initialLocale: 'en',
        signedIn: true,
        children: createElement('main', null, 'Synthetic family content'),
      }),
    );
    const signedOut = renderToStaticMarkup(
      createElement(SurfaceShell, {
        surface: 'family',
        initialLocale: 'en',
        signedIn: false,
        children: createElement('main', null, 'Synthetic family content'),
      }),
    );

    expect(signedIn).toContain('action="/backend/auth/logout"');
    expect(signedIn).toContain('method="post"');
    expect(signedIn).toContain('Sign out');
    expect(signedOut).not.toContain('/backend/auth/logout');
  });

  it('provides a localized skip link and stable main-content target', () => {
    const markup = renderToStaticMarkup(
      createElement(SurfaceShell, {
        surface: 'care',
        initialLocale: 'en',
        signedIn: false,
        children: createElement('main', null, 'Synthetic care content'),
      }),
    );

    expect(markup).toContain('href="#surface-main-content"');
    expect(markup).toContain('Skip to main content');
    expect(markup).toContain('id="surface-main-content"');
    expect(markup).toContain('Care workspace');
  });
});
