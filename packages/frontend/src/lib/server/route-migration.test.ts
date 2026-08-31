import { describe, expect, it } from 'vitest';
import { strictRelativeReturnTo } from './oauth-transaction';

/**
 * The two places a route lives outside `app/`, and the two that fail quietly
 * when it moves: a stale redirect just 404s, and a stale sign-in allowlist
 * silently drops the visitor on `/onboarding/resolve` instead of where they
 * were going. Neither shows up in a page test.
 */
type Redirect = { source: string; destination: string; permanent: boolean };

/* next.config.mjs is plain JS and tsconfig sets `allowJs: false`, so any
   specifier TypeScript can resolve statically trips TS7016. A URL built at
   runtime is opaque to the checker and still a normal ESM import to Node,
   which keeps the config readable here without loosening tsconfig for the
   whole package. */
type NextConfigModule = { default: { redirects?: () => Promise<Redirect[]> } };

const CONFIG_URL = new URL('../../../next.config.mjs', import.meta.url).href;

async function redirects(): Promise<Redirect[]> {
  const loaded = (await import(/* @vite-ignore */ CONFIG_URL)) as NextConfigModule;
  return (await loaded.default.redirects?.()) ?? [];
}

describe('legacy route redirects', () => {
  it.each([
    ['/dashboard', '/staff'],
    ['/dashboard/assignments', '/staff/assignments'],
    ['/dashboard/:elderId', '/staff/elders/:elderId'],
    ['/consent', '/elder/consent'],
  ])('%s still resolves to %s', async (source, destination) => {
    const rule = (await redirects()).find((entry) => entry.source === source);

    expect(rule, `no redirect declared for ${source}`).toBeDefined();
    expect(rule?.destination).toBe(destination);
  });

  /* Next matches redirects in order, and `/dashboard/:elderId` also matches
     `/dashboard/assignments`. If the dynamic rule is ever moved above the
     static one, the assignments bookmark lands on /staff/elders/assignments —
     a 404 that looks like a routing bug rather than an ordering one. */
  it('matches the assignments rule before the elder-id pattern', async () => {
    const sources = (await redirects()).map((entry) => entry.source);

    expect(sources.indexOf('/dashboard/assignments')).toBeLessThan(
      sources.indexOf('/dashboard/:elderId'),
    );
  });

  /* Temporary while the information architecture settles: a permanent redirect
     is cached by the browser indefinitely and cannot be taken back. */
  it('keeps the redirects temporary', async () => {
    for (const rule of await redirects()) {
      expect(rule.permanent, `${rule.source} is permanent`).toBe(false);
    }
  });
});

describe('post-sign-in return allowlist', () => {
  it.each(['/', '/elder/consent', '/staff', '/family', '/account/sign-in-methods'])(
    'accepts %s',
    (path) => {
      expect(strictRelativeReturnTo(path)).toBe(path);
    },
  );

  /* The moved paths are gone from the allowlist on purpose. Accepting a URL the
     app no longer serves would only widen what has to be reasoned about. */
  it.each(['/dashboard', '/consent'])('no longer accepts the retired %s', (path) => {
    expect(strictRelativeReturnTo(path)).toBeNull();
  });

  it('still refuses anything off-origin or unlisted', () => {
    expect(strictRelativeReturnTo('//evil.example')).toBeNull();
    expect(strictRelativeReturnTo('https://evil.example/staff')).toBeNull();
    expect(strictRelativeReturnTo('/staff/elders/1')).toBeNull();
    expect(strictRelativeReturnTo('/staff?next=/evil')).toBeNull();
  });
});
