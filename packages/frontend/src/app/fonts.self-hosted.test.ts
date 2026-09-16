import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * MASTER.md §5: Figtree and Noto Sans TC are served from our own domain, never
 * from Google Fonts (offline availability, no visitor IP sent to a CDN). The
 * faces went months without any @font-face at all — every page silently
 * rendered in the system font — so this pins the wiring, not just the intent.
 */

const here = (relative: string) => fileURLToPath(new URL(relative, import.meta.url));
const globals = readFileSync(here('./globals.css'), 'utf8');
const layout = readFileSync(here('./layout.tsx'), 'utf8');
const notoCss = readFileSync(here('./fonts/noto-sans-tc.css'), 'utf8');

describe('self-hosted typography', () => {
  it('puts Figtree (via next/font/local) first and Noto Sans TC second in the stack', () => {
    expect(globals).toMatch(/--font-sans:\s*var\(--font-figtree\),\s*'Noto Sans TC'/);
    expect(layout).toMatch(/from 'next\/font\/local'/);
    expect(layout).toMatch(/variable:\s*'--font-figtree'/);
    expect(layout).toMatch(/className=\{figtree\.variable\}/);
    expect(existsSync(here('./fonts/figtree-variable.woff2'))).toBe(true);
  });

  it('declares every Noto Sans TC slice with a file that exists, swap display and a unicode-range', () => {
    const faces = notoCss.match(/@font-face\s*\{[^}]*\}/g) ?? [];
    expect(faces.length).toBeGreaterThan(50);
    const sliceDir = here('../../public/fonts/noto-sans-tc/v1/');
    const files = new Set(readdirSync(sliceDir));
    for (const face of faces) {
      expect(face).toMatch(/font-display:\s*swap/);
      expect(face).toMatch(/unicode-range:\s*U\+/);
      const file = /url\('\/fonts\/noto-sans-tc\/v1\/([^']+)'\)/.exec(face)?.[1];
      expect(file, face).toBeDefined();
      expect(files.has(file as string), `missing slice ${file}`).toBe(true);
    }
  });

  it('never references a font CDN', () => {
    for (const source of [globals, layout, notoCss]) {
      expect(source).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com/);
    }
  });
});
