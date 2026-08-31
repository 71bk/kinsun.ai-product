/**
 * Production visual QA for the three unauthenticated auth entry points.
 *
 *   npm run qa:auth --workspace @elderly-care/frontend -- http://127.0.0.1:3105
 *
 * Covers /elder/start, /family/sign-in and /staff/sign-in across the phone
 * widths required by AGENTS.md (375/390/430) plus desktop, in both UI locales.
 * Follows the same audit rules as care-visual-qa.mjs: no horizontal overflow,
 * no sub-48px touch targets, no unnamed icon-only controls.
 */

import { mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const BASE = process.argv[2] ?? 'http://127.0.0.1:3105';
const OUT = fileURLToPath(new URL('../.visual-qa-auth/', import.meta.url));

const VIEWPORTS = [
  { name: '375-phone', width: 375, height: 812 },
  { name: '390-phone', width: 390, height: 844 },
  { name: '430-phone', width: 430, height: 932 },
  { name: '1440-desktop', width: 1440, height: 900 },
];

const LOCALES = ['zh-Hant', 'en'];

function audit() {
  const doc = document.documentElement;
  const visible = (element) => element.getClientRects().length > 0;

  const smallTargets = [...document.querySelectorAll('a,button,input,select,textarea')]
    .filter(visible)
    .map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        tag: element.tagName.toLowerCase(),
        text: (element.textContent ?? '').trim().slice(0, 24),
        height: Math.round(rect.height),
      };
    })
    .filter((target) => target.height > 0 && target.height < 48);

  const iconOnly = [...document.querySelectorAll('a,button')].filter((element) => {
    const hasGraphic = element.querySelector('svg,img') !== null;
    const hasText = (element.textContent ?? '').trim().length > 0;
    const hasName = element.hasAttribute('aria-label') || element.hasAttribute('aria-labelledby');
    return visible(element) && hasGraphic && !hasText && !hasName;
  });

  // Every visible input must be associated with a label (explicit or aria).
  const unlabelledInputs = [...document.querySelectorAll('input')]
    .filter((element) => visible(element) && element.type !== 'hidden')
    .filter((element) => {
      if (element.hasAttribute('aria-label') || element.hasAttribute('aria-labelledby')) return false;
      return element.id ? document.querySelector(`label[for="${CSS.escape(element.id)}"]`) === null : true;
    })
    .map((element) => element.name || element.type);

  return {
    clientWidth: doc.clientWidth,
    scrollWidth: doc.scrollWidth,
    innerWidth: window.innerWidth,
    h1Count: document.querySelectorAll('h1').length,
    smallTargets,
    iconOnlyCount: iconOnly.length,
    unlabelledInputs,
    text: document.body.innerText,
  };
}

async function capture(page, state, viewport, locale, problems, expectations = []) {
  await page.waitForTimeout(200);
  const result = await page.evaluate(audit);

  if (result.scrollWidth > result.clientWidth + 1) {
    problems.push(
      `${state}: horizontal overflow scrollWidth=${result.scrollWidth} > clientWidth=${result.clientWidth}`,
    );
  }
  if (result.innerWidth !== viewport.width) {
    problems.push(`${state}: viewport drift innerWidth=${result.innerWidth} expected ${viewport.width}`);
  }
  if (result.smallTargets.length > 0) {
    problems.push(
      `${state}: targets under 48px: ${result.smallTargets
        .slice(0, 5)
        .map((target) => `${target.tag}"${target.text}"=${target.height}px`)
        .join(', ')}`,
    );
  }
  if (result.iconOnlyCount > 0) {
    problems.push(`${state}: ${result.iconOnlyCount} unnamed icon control(s)`);
  }
  if (result.unlabelledInputs.length > 0) {
    problems.push(`${state}: unlabelled input(s): ${result.unlabelledInputs.join(', ')}`);
  }
  if (result.h1Count !== 1) {
    problems.push(`${state}: expected exactly one <h1>, found ${result.h1Count}`);
  }
  for (const expected of expectations) {
    if (!result.text.includes(expected)) {
      problems.push(`${state}: missing expected copy "${expected}"`);
    }
  }

  await page.screenshot({
    path: join(OUT, `${state}__${viewport.name}__${locale}.png`),
    fullPage: true,
  });
  return result;
}

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const rows = [];
let failures = 0;

for (const viewport of VIEWPORTS) {
  for (const locale of LOCALES) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 1,
      reducedMotion: 'reduce',
    });
    await context.addCookies([
      { name: 'kinsun_ui_locale', value: locale, domain: new URL(BASE).hostname, path: '/' },
    ]);
    const page = await context.newPage();
    const problems = [];
    const consoleErrors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text().slice(0, 160));
    });
    page.on('pageerror', (error) => consoleErrors.push(`pageerror: ${String(error).slice(0, 160)}`));

    try {
      // --- /elder/start : login mode (default) ---
      await page.goto(`${BASE}/elder/start`, { waitUntil: 'load', timeout: 90_000 });
      await page.locator('h1').waitFor({ timeout: 20_000 });
      await capture(page, 'elder-start-login', viewport, locale, problems, ['小暖 Kinsun']);

      // --- /elder/start : register mode (client-side tab) ---
      /* 146b090 turned this from a "建立帳號" button into a tablist, so the old
         button selector matched nothing and reported a missing control on every
         viewport. Assert the tab's own selected state rather than a heading:
         both modes share the "開始使用 Kinsun" heading, so a heading wait would
         pass without the tab having switched. */
      const toggle = page.getByRole('tab', { name: '註冊' });
      if ((await toggle.count()) > 0) {
        await toggle.first().click();
        await page
          .getByRole('tab', { name: '註冊', selected: true })
          .waitFor({ timeout: 10_000 });
        await capture(page, 'elder-start-register', viewport, locale, problems);
      } else {
        problems.push('elder-start: register tab not found');
      }

      // --- /elder/start : password visibility toggle ---
      await page.goto(`${BASE}/elder/start?v=pw`, { waitUntil: 'load', timeout: 90_000 });
      const pwToggle = page.locator('button[aria-pressed]').first();
      if ((await pwToggle.count()) > 0) {
        await pwToggle.click();
        const revealed = await page.locator('input[name="password"]').getAttribute('type');
        if (revealed !== 'text') {
          problems.push(`elder-start: password toggle did not reveal (type=${revealed})`);
        }
        await capture(page, 'elder-start-password-shown', viewport, locale, problems);
      } else {
        problems.push('elder-start: password visibility toggle not found');
      }

      // --- /family/sign-in ---
      await page.goto(`${BASE}/family/sign-in`, { waitUntil: 'load', timeout: 90_000 });
      await page.locator('h1').waitFor({ timeout: 20_000 });
      await capture(page, 'family-sign-in', viewport, locale, problems);

      // --- /staff/sign-in ---
      await page.goto(`${BASE}/staff/sign-in`, { waitUntil: 'load', timeout: 90_000 });
      await page.locator('h1').waitFor({ timeout: 20_000 });
      await capture(page, 'staff-sign-in', viewport, locale, problems);

      // --- keyboard focus reachability on the staff form ---
      await page.keyboard.press('Tab');
      const firstFocus = await page.evaluate(() => {
        const el = document.activeElement;
        return el ? `${el.tagName.toLowerCase()}:${(el.textContent ?? '').trim().slice(0, 20)}` : 'none';
      });
      if (firstFocus === 'none' || firstFocus.startsWith('body')) {
        problems.push(`staff-sign-in: first Tab did not reach a focusable control (${firstFocus})`);
      }
    } catch (error) {
      const body = await page
        .locator('body')
        .innerText()
        .catch(() => '');
      problems.push(`LOAD FAILED: ${String(error).split('\n')[0]} | ${body.slice(0, 200)}`);
      await page
        .screenshot({ path: join(OUT, `failure__${viewport.name}__${locale}.png`), fullPage: true })
        .catch(() => undefined);
    }

    if (consoleErrors.length > 0) {
      problems.push(`console errors: ${[...new Set(consoleErrors)].slice(0, 3).join(' | ')}`);
    }
    if (problems.length > 0) failures += 1;
    rows.push({ viewport: viewport.name, locale, problems });
    await context.close();
  }
}

await browser.close();

for (const row of rows) {
  console.log(`${row.problems.length === 0 ? 'PASS' : 'FAIL'}  ${row.viewport.padEnd(14)} ${row.locale}`);
  for (const problem of row.problems) console.log(`      - ${problem}`);
}
console.log(`\n${failures} failing viewport/locale combination(s) of ${rows.length}`);
console.log(`screenshots: ${OUT}`);
if (failures > 0) process.exitCode = 1;
