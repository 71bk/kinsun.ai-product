/**
 * Synthetic visual QA for the staff-assisted Elder tablet handoff.
 *
 *   node scripts/assisted-visual-qa.mjs [baseUrl]
 *
 * Run against `next build && next start`, not the dev server. Network fixtures
 * are deliberately synthetic: this script checks rendered states and browser
 * boundaries without reading or mutating Core/Supabase data.
 */

import { mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const BASE = process.argv[2] ?? 'http://localhost:3000';
const ONLY_STATE = process.argv[3];
const ONLY_VIEWPORT = process.argv[4];
const OUT = fileURLToPath(new URL('../.visual-qa-assisted/', import.meta.url));
const TOKEN = `ep1_${'A'.repeat(43)}`;

const VIEWPORTS = [
  { name: '375-phone', width: 375, height: 812 },
  { name: '390-phone', width: 390, height: 844 },
  { name: '430-phone', width: 430, height: 932 },
  { name: '1440-desktop', width: 1440, height: 900 },
];

const REQUIRED = {
  status: 'REQUIRED',
  policy_version: 'synthetic-consent-v1',
  consent_version: null,
  acknowledged_at: null,
  confirmation_method: null,
};

const ACKNOWLEDGED = {
  status: 'ACKNOWLEDGED',
  policy_version: 'synthetic-consent-v1',
  consent_version: 1,
  acknowledged_at: '2026-09-01T04:00:00Z',
  confirmation_method: 'ASSISTED_TABLET_ACKNOWLEDGEMENT',
};

function session(firstUse) {
  return {
    assisted_session_id: '79000000-0000-4000-8000-000000000001',
    elder_id: '75000000-0000-4000-8000-000000000001',
    display_name: '測試長者',
    preferred_name: '林奶奶',
    status: 'ACTIVE',
    idle_expires_at: '2026-09-01T04:30:00Z',
    absolute_expires_at: '2026-09-01T12:00:00Z',
    first_use_acknowledgement: firstUse,
  };
}

function envelope(data) {
  return {
    data,
    meta: {
      correlation_id: '76000000-0000-4000-8000-000000000001',
      timestamp: '2026-09-01T04:00:00Z',
      schema_version: '1.0',
    },
  };
}

async function fulfillJson(route, data, status = 200) {
  await route.fulfill({
    body: JSON.stringify(data),
    contentType: 'application/json',
    status,
  });
}

async function installSyntheticRoutes(page, sessionState) {
  await page.route('**/backend/**', async (route) => {
    const request = route.request();
    const method = request.method();
    const pathname = new URL(request.url()).pathname;

    if (pathname === '/backend/auth/session') {
      await fulfillJson(route, { credential_present: true });
      return;
    }

    if (pathname === '/backend/elder-session/current' && method === 'GET') {
      if (sessionState === 'ended') {
        await fulfillJson(route, { error: { message: 'Authentication required' } }, 401);
      } else {
        await fulfillJson(
          route,
          envelope(session(sessionState === 'required' ? REQUIRED : ACKNOWLEDGED)),
        );
      }
      return;
    }

    if (pathname === '/backend/elder-session/current' && method === 'DELETE') {
      await route.fulfill({ status: 204 });
      return;
    }

    if (pathname === '/backend/elder-session/companion-turns') {
      await fulfillJson(
        route,
        envelope({
          reply_text: '林奶奶，我在這裡陪您慢慢聊。',
          result_status: 'SUCCESS',
          safety_decision: 'ALLOW',
        }),
      );
      return;
    }

    if (pathname === '/backend/elder-session/acknowledgement') {
      await fulfillJson(route, envelope(method === 'DELETE' ? REQUIRED : ACKNOWLEDGED));
      return;
    }

    if (pathname === '/backend/core/api/v1/me') {
      await fulfillJson(
        route,
        envelope({
          role: 'DAYCARE_CARE_WORKER',
          display_name: '合成照服員',
          tenant_id: '71000000-0000-4000-8000-000000000001',
          care_unit_ids: ['73000000-0000-4000-8000-000000000001'],
        }),
      );
      return;
    }

    if (pathname === '/backend/core/api/v1/me/authorized-elders') {
      await fulfillJson(
        route,
        envelope({ items: [], page: { next_cursor: null, has_more: false, limit: 100 } }),
      );
      return;
    }

    if (/\/backend\/core\/api\/v1\/organizations\/[^/]+\/elders$/.test(pathname)) {
      await fulfillJson(
        route,
        envelope({
          elder_id: '75000000-0000-4000-8000-000000000001',
          actor_id: null,
          enrollment_id: '77000000-0000-4000-8000-000000000001',
          display_name: '林奶奶',
          preferred_name: '林奶奶',
        }),
        201,
      );
      return;
    }

    if (/\/backend\/core\/api\/v1\/elders\/[^/]+\/assisted-sessions$/.test(pathname)) {
      await fulfillJson(
        route,
        envelope({
          assisted_session_id: '79000000-0000-4000-8000-000000000001',
          elder_id: '75000000-0000-4000-8000-000000000001',
          pairing_token: TOKEN,
          pairing_expires_at: '2026-09-01T04:15:00Z',
          absolute_expires_at: '2026-09-01T12:00:00Z',
        }),
        201,
      );
      return;
    }

    await route.continue();
  });
}

function auditPage() {
  const root = document.documentElement;
  const surfaces = [...document.querySelectorAll('[data-surface]')];
  const surface = surfaces.at(-1)?.getAttribute('data-surface') ?? null;
  const minimum = surface === 'voice' ? 64 : 48;
  const visible = (element) => element.getClientRects().length > 0;
  const targets = [...document.querySelectorAll('a,button,input,select,textarea')]
    .filter(visible)
    .map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        tag: element.tagName.toLowerCase(),
        text: (element.textContent || element.getAttribute('aria-label') || '').trim().slice(0, 36),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      };
    });
  const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((heading) =>
    Number(heading.tagName[1]),
  );
  const skipLink = [...document.querySelectorAll('a')].find((link) =>
    (link.textContent ?? '').includes('跳到主要內容'),
  );
  const skipRect = skipLink?.getBoundingClientRect();

  return {
    activeElement: {
      ariaLive: document.activeElement?.getAttribute('aria-live'),
      tag: document.activeElement?.tagName.toLowerCase(),
      text: (document.activeElement?.textContent ?? '').trim().slice(0, 80),
    },
    surface,
    minimum,
    clientWidth: root.clientWidth,
    scrollWidth: root.scrollWidth,
    bodyFontSize: parseFloat(getComputedStyle(document.body).fontSize),
    reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
    scrollY: Math.round(window.scrollY),
    skipLink: skipLink
      ? {
          focusVisible: skipLink.matches(':focus-visible'),
          top: Math.round(skipRect.top),
          transform: getComputedStyle(skipLink).transform,
        }
      : null,
    targets,
    headings,
  };
}

function headingSkips(levels) {
  const problems = [];
  let previous = 0;
  for (const level of levels) {
    if (previous > 0 && level > previous + 1) problems.push(`h${previous} -> h${level}`);
    previous = level;
  }
  return problems;
}

const STATES = [
  {
    name: 'pair-default',
    path: '/elder/pair',
    surface: 'voice',
    expectText: ['開啟小暖陪伴', '一次性平板連結', '連結只能使用一次'],
    singleLineHeading: '開啟小暖陪伴',
  },
  {
    name: 'pair-invalid',
    path: '/elder/pair',
    surface: 'voice',
    expectText: ['連結無效、已使用或已過期'],
    action: async (page) => {
      await page.getByLabel('一次性平板連結').fill('不是有效連結');
      await page.getByRole('button', { name: /進入長者模式/ }).click();
      await page.getByText('連結無效、已使用或已過期，請照顧員重新產生。').waitFor();
    },
  },
  {
    name: 'session-ended',
    path: '/elder/session',
    sessionState: 'ended',
    surface: 'voice',
    expectText: ['長者模式已結束', '前往平板設定'],
  },
  {
    name: 'session-required',
    path: '/elder/session',
    sessionState: 'required',
    surface: 'voice',
    expectText: ['林奶奶，開始前先說明', '使用 AI 陪伴前，請先了解', '現在不要使用'],
  },
  {
    name: 'session-active',
    path: '/elder/session',
    sessionState: 'active',
    surface: 'voice',
    expectText: ['林奶奶，您好', '今天想聊些什麼？', '停止 AI 陪伴'],
  },
  {
    name: 'session-conversation',
    path: '/elder/session',
    sessionState: 'active',
    surface: 'voice',
    expectText: ['今天天氣真好', '林奶奶，我在這裡陪您慢慢聊。'],
    action: async (page) => {
      await page.getByLabel('想對小暖說的話').fill('今天天氣真好');
      await page.getByRole('button', { name: '送出' }).click();
      await page.getByText('林奶奶，我在這裡陪您慢慢聊。').waitFor();
    },
  },
  {
    name: 'session-stop-confirmation',
    path: '/elder/session',
    sessionState: 'active',
    surface: 'voice',
    expectText: ['確定要停止 AI 陪伴嗎？', '繼續使用', '確定停止 AI 陪伴'],
    action: async (page) => {
      await page.getByRole('button', { name: '停止 AI 陪伴' }).click();
      await page.getByRole('heading', { name: '確定要停止 AI 陪伴嗎？' }).waitFor();
    },
  },
  {
    name: 'staff-create',
    path: '/staff/elders/new',
    surface: 'care',
    expectText: ['建立無帳號長者', 'Care Profile', '建立並產生平板交付連結'],
  },
  {
    name: 'staff-handoff',
    path: '/staff/elders/new',
    surface: 'care',
    expectText: ['長者資料已建立', '一次性平板連結', '平板啟用後只會取得短效長者模式'],
    expectFocusedLiveRegion: true,
    expectScrollTop: true,
    action: async (page) => {
      await page.getByLabel('長者姓名／顯示名稱').fill('林奶奶');
      await page.getByLabel('希望小暖怎麼稱呼').fill('林奶奶');
      await page.getByRole('button', { name: '建立並產生平板交付連結' }).click();
      await page.getByRole('heading', { name: '長者資料已建立' }).waitFor();
    },
  },
];

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const results = [];
let failures = 0;

for (const viewport of VIEWPORTS.filter((item) => !ONLY_VIEWPORT || item.name === ONLY_VIEWPORT)) {
  for (const state of STATES.filter((item) => !ONLY_STATE || item.name === ONLY_STATE)) {
    const context = await browser.newContext({
      deviceScaleFactor: 1,
      reducedMotion: 'reduce',
      viewport: { width: viewport.width, height: viewport.height },
    });
    const page = await context.newPage();
    await installSyntheticRoutes(page, state.sessionState);

    const problems = [];
    try {
      await page.goto(`${BASE}${state.path}?visualQa=${viewport.name}-${state.name}`, {
        timeout: 90_000,
        waitUntil: 'load',
      });
      await page.waitForTimeout(500);
      if (state.action) await state.action(page);
      await page.getByText(state.expectText[0], { exact: false }).first().waitFor({ timeout: 10_000 });
      await page.waitForTimeout(200);

      for (const text of state.expectText) {
        if ((await page.getByText(text, { exact: false }).count()) === 0) {
          problems.push(`missing text: ${text}`);
        }
      }

      if (state.singleLineHeading) {
        const lineCount = await page
          .getByRole('heading', { name: state.singleLineHeading })
          .evaluate((heading) => {
            const range = document.createRange();
            range.selectNodeContents(heading);
            return range.getClientRects().length;
          });
        if (lineCount !== 1) problems.push(`${state.singleLineHeading} wraps to ${lineCount} lines`);
      }

      const audit = await page.evaluate(auditPage);
      if (audit.surface !== state.surface) {
        problems.push(`surface ${audit.surface} != ${state.surface}`);
      }
      if (audit.scrollWidth > audit.clientWidth + 1) {
        problems.push(`horizontal scroll ${audit.scrollWidth} > ${audit.clientWidth}`);
      }
      if (state.surface === 'voice' && audit.bodyFontSize < 22) {
        problems.push(`voice body font ${audit.bodyFontSize}px < 22px`);
      }
      if (!audit.reducedMotion) problems.push('reduced motion media query not active');
      if (audit.skipLink && audit.skipLink.top >= 0) {
        problems.push(
          `skip link remains visible (top=${audit.skipLink.top}, focusVisible=${audit.skipLink.focusVisible}, transform=${audit.skipLink.transform})`,
        );
      }
      if (state.expectFocusedLiveRegion && audit.activeElement.ariaLive !== 'polite') {
        problems.push(
          `success live region is not focused (active ${audit.activeElement.tag}:${audit.activeElement.text})`,
        );
      }
      if (state.expectScrollTop && audit.scrollY !== 0) {
        problems.push(`success state did not return to top (scrollY=${audit.scrollY})`);
      }

      const tooSmall = audit.targets.filter((target) => target.height < audit.minimum);
      if (tooSmall.length > 0) {
        problems.push(
          `${tooSmall.length} target(s) under ${audit.minimum}px: ${tooSmall
            .slice(0, 4)
            .map((target) => `${target.tag}:${target.text || '(no text)'}=${target.height}px`)
            .join(', ')}`,
        );
      }

      const skips = headingSkips(audit.headings);
      if (skips.length > 0) problems.push(`heading skip: ${skips.join(', ')}`);

      await page.screenshot({
        path: join(OUT, `${state.name}__${viewport.name}__viewport.png`),
      });
      await page.screenshot({
        fullPage: true,
        path: join(OUT, `${state.name}__${viewport.name}.png`),
      });
    } catch (error) {
      problems.push(`load/action failed: ${String(error).split('\n')[0]}`);
    }

    if (problems.length > 0) failures += 1;
    results.push({ viewport: viewport.name, state: state.name, problems });
    await context.close();
  }
}

await browser.close();

for (const result of results) {
  console.log(
    `${result.problems.length === 0 ? 'PASS' : 'FAIL'}  ${result.viewport.padEnd(16)} ${result.state}`,
  );
  for (const problem of result.problems) console.log(`        - ${problem}`);
}
console.log(`\n${failures} failing state/viewport combination(s) of ${results.length}`);
console.log(`screenshots: ${OUT}`);

if (failures > 0) process.exitCode = 1;
