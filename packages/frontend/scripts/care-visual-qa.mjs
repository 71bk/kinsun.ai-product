/**
 * Production visual QA for authenticated Care Surface states.
 *
 *   npm run qa:care --workspace @elderly-care/frontend -- http://127.0.0.1:3105
 *
 * Browser requests are fulfilled with contract-shaped fixtures. This keeps the
 * check deterministic and prevents the test from needing a real credential,
 * while still exercising the production client, BFF paths, responsive CSS,
 * tabs, modal behavior, and non-disclosure rules.
 */

import { mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const BASE = process.argv[2] ?? 'http://127.0.0.1:3000';
const ONLY_VIEWPORT = process.argv[3];
const OUT = fileURLToPath(new URL('../.visual-qa-care/', import.meta.url));
const ELDER_ID = '11111111-1111-4111-8111-111111111111';
const FORBIDDEN_ID = 'forbidden';
const PRIVATE_NAME = '不應顯示的私人姓名';
const OPAQUE_REFERENCES = ['evt-ref-private-001', 'evt-ref-private-002'];
const RAW_TRANSCRIPT = '這是一段不應出現在照護介面的完整逐字稿';

const VIEWPORTS = [
  { name: '390-phone', width: 390, height: 844 },
  { name: '768-tablet', width: 768, height: 1024 },
  { name: '1024-landscape', width: 1024, height: 768 },
  { name: '1280-desktop', width: 1280, height: 900 },
];

const LOCALES = ['zh-Hant', 'en'];
const ELDER = {
  elder_id: ELDER_ID,
  display_name: '林美好',
  primary_care_setting: 'HOME_CARE',
  status: 'ACTIVE',
};
const ACCESS = {
  purpose: 'HOME_CARE_VISIT',
  allowed_actions: [
    'care-event:read',
    'care-event:review',
    'care_action:create',
    'care_action:read',
    'care_action:update',
    'memory:read',
    'summary:review',
  ],
  source_type: 'assignment',
  source_summary: '今日居家照護任務',
  expires_at: '2026-08-13T10:00:00Z',
};
const EVENTS = [
  {
    event_id: 'event-candidate-001',
    elder_id: ELDER_ID,
    event_type: 'MEAL',
    event_time: '2026-08-13T01:10:00Z',
    status: 'CANDIDATE',
    structured_payload: { summary: '早餐紀錄仍待照護人員確認。' },
    evidence_refs: [OPAQUE_REFERENCES[0]],
    confidence_band: 'MEDIUM',
    version: 1,
    consent_version: 3,
    created_at: '2026-08-13T01:12:00Z',
    updated_at: '2026-08-13T01:12:00Z',
  },
  {
    event_id: 'event-review-001',
    elder_id: ELDER_ID,
    event_type: 'ACTIVITY',
    event_time: '2026-08-13T02:20:00Z',
    status: 'NEEDS_REVIEW',
    structured_payload: { summary: '活動參與內容需要人工複核。' },
    evidence_refs: [OPAQUE_REFERENCES[1]],
    confidence_band: 'LOW',
    version: 2,
    consent_version: 3,
    created_at: '2026-08-13T02:22:00Z',
    updated_at: '2026-08-13T02:22:00Z',
  },
  {
    event_id: 'event-verified-001',
    elder_id: ELDER_ID,
    event_type: 'SOCIAL_CONTACT',
    event_time: '2026-08-13T03:30:00Z',
    status: 'VERIFIED',
    structured_payload: { summary: '已確認今日與家人通話。' },
    evidence_refs: [],
    confidence_band: 'HIGH',
    version: 4,
    consent_version: 3,
    created_at: '2026-08-13T03:32:00Z',
    updated_at: '2026-08-13T03:32:00Z',
  },
];
const MEMORIES = {
  candidates: [
    {
      memory_id: 'memory-candidate-001',
      elder_id: ELDER_ID,
      memory_type: 'PREFERENCE',
      content: '偏好在早餐後散步，尚待本人確認。',
      status: 'CANDIDATE',
      source_event_ids: [OPAQUE_REFERENCES[0]],
      confirmed_by: null,
      confirmed_at: null,
      version: 1,
      active_from: null,
      inactive_at: null,
      consent_version: 3,
      created_at: '2026-08-12T01:00:00Z',
      updated_at: '2026-08-12T01:00:00Z',
    },
  ],
  active: [
    {
      memory_id: 'memory-active-001',
      elder_id: ELDER_ID,
      memory_type: 'COMMUNICATION_PREFERENCE',
      content: '已確認偏好使用台語交談。',
      status: 'ACTIVE',
      source_event_ids: [],
      confirmed_by: 'actor-private-001',
      confirmed_at: '2026-08-10T08:00:00Z',
      version: 2,
      active_from: '2026-08-10T08:00:00Z',
      inactive_at: null,
      consent_version: 3,
      created_at: '2026-08-10T08:00:00Z',
      updated_at: '2026-08-10T08:00:00Z',
    },
  ],
};
const SUMMARIES = [
  {
    summary_id: 'summary-draft-001',
    elder_id: ELDER_ID,
    summary_date: '2026-08-13',
    summary_type: 'PROFESSIONAL_DAILY',
    status: 'NEEDS_REVIEW',
    items: [
      {
        category: 'MEAL',
        text: '早餐資訊來自待確認事件，請照護人員複核。',
        source_event_ids: [OPAQUE_REFERENCES[0]],
        data_status: 'PRESENT',
      },
      {
        category: 'SLEEP',
        text: '今日沒有足夠資料。',
        source_event_ids: [],
        data_status: 'INSUFFICIENT',
      },
    ],
    missing_fields: ['sleep'],
    conflict_flags: ['meal-source-unverified'],
    version: 2,
    generated_at: '2026-08-13T04:00:00Z',
    created_at: '2026-08-13T04:00:00Z',
    updated_at: '2026-08-13T04:00:00Z',
  },
  {
    summary_id: 'summary-ready-001',
    elder_id: ELDER_ID,
    summary_date: '2026-08-12',
    summary_type: 'PROFESSIONAL_DAILY',
    status: 'READY',
    items: [
      {
        category: 'SOCIAL',
        text: '已確認與家人保持聯繫。',
        source_event_ids: [],
        data_status: 'PRESENT',
      },
    ],
    missing_fields: [],
    conflict_flags: [],
    version: 3,
    generated_at: '2026-08-12T09:00:00Z',
    created_at: '2026-08-12T09:00:00Z',
    updated_at: '2026-08-12T09:00:00Z',
  },
];
const CARE_ACTIONS = [
  {
    care_action_id: 'care-action-open-001',
    elder_id: ELDER_ID,
    action_type: 'FOLLOW_UP',
    title: '追蹤下次聯繫安排',
    description: '確認長者方便接聽的時段。',
    trigger_reason: '已覆核事件顯示今日完成家人通話，需要確認下次聯繫安排。',
    related_event_ids: ['event-verified-001'],
    assignee_actor_id: 'worker-private-001',
    due_at: '2026-09-03T01:00:00Z',
    priority: 'MEDIUM',
    status: 'OPEN',
    resolution: null,
    created_by_actor_id: 'worker-private-001',
    version: 1,
    created_at: '2026-09-02T01:00:00Z',
    updated_at: '2026-09-02T01:00:00Z',
  },
  {
    care_action_id: 'care-action-postponed-001',
    elder_id: ELDER_ID,
    action_type: 'INVITE_ACTIVITY',
    title: '邀請參加下週活動',
    description: null,
    trigger_reason: '已覆核事件顯示長者有興趣參加團體活動。',
    related_event_ids: ['event-verified-001'],
    assignee_actor_id: 'worker-private-001',
    due_at: '2026-09-05T01:00:00Z',
    priority: 'LOW',
    status: 'POSTPONED',
    resolution: '長者今日外出，改於下次服務時確認。',
    created_by_actor_id: 'worker-private-001',
    version: 2,
    created_at: '2026-09-01T01:00:00Z',
    updated_at: '2026-09-02T02:00:00Z',
  },
  {
    care_action_id: 'care-action-completed-001',
    elder_id: ELDER_ID,
    action_type: 'CONFIRM_INFORMATION',
    title: '確認家屬聯繫方式',
    description: null,
    trigger_reason: '正式事件需要補充後續聯繫資訊。',
    related_event_ids: ['event-verified-001'],
    assignee_actor_id: 'worker-private-001',
    due_at: '2026-09-02T01:00:00Z',
    priority: 'HIGH',
    status: 'COMPLETED',
    resolution: '已由照護者完成資訊確認。',
    created_by_actor_id: 'worker-private-001',
    version: 3,
    created_at: '2026-08-31T01:00:00Z',
    updated_at: '2026-09-02T03:00:00Z',
  },
];
const ASSIGNMENTS = [
  {
    assignment_id: 'assignment-confirmed-001',
    elder_id: ELDER_ID,
    provider_tenant_id: 'tenant-private-001',
    care_unit_id: 'unit-private-001',
    home_care_worker_id: 'worker-private-001',
    scheduled_start: '2026-08-13T01:00:00Z',
    scheduled_end: '2026-08-13T03:00:00Z',
    status: 'CONFIRMED',
    allowed_data_scopes: ['care-event:read', 'care-event:write'],
    version: 1,
    expires_at: '2026-08-13T04:00:00Z',
  },
  {
    assignment_id: 'assignment-active-001',
    elder_id: ELDER_ID,
    provider_tenant_id: 'tenant-private-001',
    care_unit_id: 'unit-private-001',
    home_care_worker_id: 'worker-private-001',
    scheduled_start: '2026-08-13T05:00:00Z',
    scheduled_end: '2026-08-13T07:00:00Z',
    status: 'IN_PROGRESS',
    allowed_data_scopes: ['care-event:read'],
    version: 2,
    expires_at: '2026-08-13T08:00:00Z',
  },
];

function envelope(data) {
  return {
    data,
    meta: {
      correlation_id: 'care-visual-qa',
      timestamp: '2026-08-13T00:00:00Z',
      schema_version: '1.0',
    },
  };
}

async function json(route, data, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(status >= 400 ? data : envelope(data)),
  });
}

async function installContractFixtures(context) {
  await context.route('**/backend/auth/session', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ credential_present: true }),
    }),
  );

  await context.route('**/backend/core/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace('/backend/core', '');

    if (request.method() !== 'GET') {
      await json(
        route,
        {
          error: { message: 'Visual QA does not submit mutations.', retryable: false },
        },
        405,
      );
      return;
    }
    if (path === '/api/v1/me') {
      await json(route, { role: 'HOME_CARE_WORKER', display_name: '王照護員' });
      return;
    }
    if (path === '/api/v1/me/authorized-elders') {
      await json(route, {
        items: [
          {
            elder_id: ELDER_ID,
            display_name: ELDER.display_name,
            care_unit_name: '安心居家照護',
            authorization_summary: '今日任務授權',
          },
          {
            elder_id: '22222222-2222-4222-8222-222222222222',
            display_name: '陳安康',
            care_unit_name: '安心居家照護',
            authorization_summary: '本週照護授權',
          },
        ],
        page: { next_cursor: 'opaque-next-page', has_more: true, limit: 100 },
      });
      return;
    }
    if (path.includes(`/elders/${FORBIDDEN_ID}`)) {
      await json(
        route,
        { error: { message: 'Resource not found.', reason_code: 'NOT_FOUND', retryable: false } },
        404,
      );
      return;
    }
    if (path === `/api/v1/elders/${ELDER_ID}`) {
      await json(route, ELDER);
      return;
    }
    if (path === `/api/v1/elders/${ELDER_ID}/access-context`) {
      await json(route, ACCESS);
      return;
    }
    if (path === `/api/v1/elders/${ELDER_ID}/care-events`) {
      const requestedStatus = url.searchParams.get('status');
      const events = requestedStatus
        ? EVENTS.filter((event) => event.status === requestedStatus)
        : EVENTS;
      await json(route, { items: events, next_cursor: null, has_more: false });
      return;
    }
    if (path === `/api/v1/elders/${ELDER_ID}/care-actions`) {
      await json(route, { items: CARE_ACTIONS, next_cursor: null, has_more: false });
      return;
    }
    if (path === `/api/v1/elders/${ELDER_ID}/memory-candidates`) {
      await json(route, { items: MEMORIES.candidates, next_cursor: null, has_more: false });
      return;
    }
    if (path === `/api/v1/elders/${ELDER_ID}/memories`) {
      await json(route, { items: MEMORIES.active, next_cursor: null, has_more: false });
      return;
    }
    if (path === `/api/v1/elders/${ELDER_ID}/summaries`) {
      await json(route, { items: SUMMARIES });
      return;
    }
    if (path === '/api/v1/home-care/assignments') {
      await json(route, { items: ASSIGNMENTS });
      return;
    }

    await json(
      route,
      { error: { message: `Unhandled visual QA path: ${path}`, retryable: false } },
      500,
    );
  });
}

function audit(leakCandidates) {
  const doc = document.documentElement;
  const visibleTargets = [...document.querySelectorAll('a,button,input,select,textarea')]
    .filter((element) => element.getClientRects().length > 0)
    .map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        tag: element.tagName.toLowerCase(),
        text: (element.textContent ?? '').trim().slice(0, 24),
        height: Math.round(rect.height),
      };
    });
  const iconOnly = [...document.querySelectorAll('a,button')].filter((element) => {
    const visible = element.getClientRects().length > 0;
    const hasGraphic = element.querySelector('svg,img') !== null;
    const hasText = (element.textContent ?? '').trim().length > 0;
    const hasName = element.hasAttribute('aria-label') || element.hasAttribute('aria-labelledby');
    return visible && hasGraphic && !hasText && !hasName;
  });
  const visibleText = document.body.innerText;

  return {
    clientWidth: doc.clientWidth,
    scrollWidth: doc.scrollWidth,
    smallTargets: visibleTargets.filter((target) => target.height > 0 && target.height < 48),
    iconOnlyCount: iconOnly.length,
    leakedText: leakCandidates.filter((value) => visibleText.includes(value)),
  };
}

async function settle(page, marker) {
  await page.waitForFunction((expected) => document.body.innerText.includes(expected), marker, {
    timeout: 20_000,
  });
  await page.waitForTimeout(250);
}

async function capture(page, viewport, locale, state, problems) {
  const result = await page.evaluate(audit, [
    'actor-private-001',
    'tenant-private-001',
    'unit-private-001',
    'worker-private-001',
    ...OPAQUE_REFERENCES,
    RAW_TRANSCRIPT,
  ]);
  if (result.scrollWidth > result.clientWidth + 1) {
    problems.push(`${state}: horizontal scroll ${result.scrollWidth} > ${result.clientWidth}`);
  }
  if (result.smallTargets.length > 0) {
    problems.push(
      `${state}: targets under 48px: ${result.smallTargets
        .slice(0, 4)
        .map((target) => `${target.tag}"${target.text}"=${target.height}px`)
        .join(', ')}`,
    );
  }
  if (result.iconOnlyCount > 0)
    problems.push(`${state}: ${result.iconOnlyCount} unnamed icon controls`);
  if (result.leakedText.length > 0)
    problems.push(`${state}: leaked ${result.leakedText.join(', ')}`);

  await page.screenshot({
    path: join(OUT, `${state}__${viewport.name}__${locale}.png`),
    fullPage: true,
  });
}

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const rows = [];
let failures = 0;

for (const viewport of VIEWPORTS.filter(
  (candidate) => !ONLY_VIEWPORT || candidate.name === ONLY_VIEWPORT,
)) {
  for (const locale of LOCALES) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 1,
      reducedMotion: 'reduce',
    });
    await installContractFixtures(context);
    await context.addCookies([
      { name: 'kinsun_ui_locale', value: locale, domain: new URL(BASE).hostname, path: '/' },
    ]);
    const page = await context.newPage();
    const problems = [];

    try {
      await page.goto(`${BASE}/staff`, { waitUntil: 'load', timeout: 90_000 });
      await settle(page, ELDER.display_name);
      await capture(page, viewport, locale, 'dashboard', problems);

      await page.goto(`${BASE}/staff/elders/${ELDER_ID}`, { waitUntil: 'load', timeout: 90_000 });
      await settle(page, '早餐紀錄仍待照護人員確認。');
      await capture(page, viewport, locale, 'elder-events', problems);

      await page.locator('#elder-tab-actions').click();
      await settle(page, '追蹤下次聯繫安排');
      await capture(page, viewport, locale, 'elder-care-actions', problems);

      await page.locator('#elder-panel-actions button[aria-expanded]').click();
      await page.locator('#elder-panel-actions input[name="title"]').waitFor({ timeout: 20_000 });
      await page.waitForTimeout(250);
      await capture(page, viewport, locale, 'elder-care-action-create', problems);
      await page.locator('#elder-panel-actions button[aria-expanded]').click();

      await page.locator('#elder-panel-actions article[data-status="OPEN"] button').first().click();
      await page.waitForSelector('dialog[open]');
      await page.screenshot({
        path: join(OUT, `elder-care-action-dialog__${viewport.name}__${locale}.png`),
        fullPage: false,
      });
      await page.keyboard.press('Escape');
      await page.waitForSelector('dialog[open]', { state: 'detached' });

      await page.locator('#elder-panel-actions article[data-status="OPEN"] button').nth(1).click();
      await page.locator('#elder-panel-actions article[data-status="OPEN"] form').waitFor();
      await capture(page, viewport, locale, 'elder-care-action-transition', problems);

      await page.locator('#elder-tab-memories').click();
      await settle(page, '偏好在早餐後散步，尚待本人確認。');
      await capture(page, viewport, locale, 'elder-memories', problems);

      await page.locator('#elder-tab-summaries').click();
      await settle(page, '早餐資訊來自待確認事件，請照護人員複核。');
      await capture(page, viewport, locale, 'elder-summaries', problems);

      await page.goto(`${BASE}/staff/assignments`, { waitUntil: 'load', timeout: 90_000 });
      await page.locator('article[data-status]').first().waitFor({ timeout: 20_000 });
      await page.waitForTimeout(250);
      await page.locator('article button').first().click();
      await page.waitForSelector('dialog[open]');
      if ((await page.locator('dialog[open]').count()) !== 1) {
        problems.push('assignments: confirmation dialog did not open');
      }
      await page.screenshot({
        path: join(OUT, `assignments-dialog__${viewport.name}__${locale}.png`),
        fullPage: false,
      });
      await page.keyboard.press('Escape');
      await page.waitForSelector('dialog[open]', { state: 'detached' });
      if ((await page.locator('dialog[open]').count()) !== 0) {
        problems.push('assignments: confirmation dialog did not close with Escape');
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await capture(page, viewport, locale, 'assignments', problems);

      await page.goto(`${BASE}/staff/elders/${FORBIDDEN_ID}`, {
        waitUntil: 'load',
        timeout: 90_000,
      });
      await page.waitForSelector('main');
      await page.waitForTimeout(350);
      if ((await page.locator(`text=${PRIVATE_NAME}`).count()) > 0) {
        problems.push('denied: elder identity was rendered');
      }
      await capture(page, viewport, locale, 'elder-denied', problems);
    } catch (error) {
      const bodyText = (
        await page
          .locator('body')
          .innerText()
          .catch(() => '')
      ).slice(0, 240);
      problems.push(`LOAD FAILED: ${String(error).split('\n')[0]} | ${bodyText}`);
      await page
        .screenshot({
          path: join(OUT, `failure__${viewport.name}__${locale}.png`),
          fullPage: true,
        })
        .catch(() => undefined);
    }

    if (problems.length > 0) failures += 1;
    rows.push({ viewport: viewport.name, locale, problems });
    await context.close();
  }
}

await browser.close();

for (const row of rows) {
  console.log(
    `${row.problems.length === 0 ? 'PASS' : 'FAIL'}  ${row.viewport.padEnd(18)} ${row.locale}`,
  );
  for (const problem of row.problems) console.log(`      - ${problem}`);
}
console.log(`\n${failures} failing viewport/locale combination(s) of ${rows.length}`);
console.log(`screenshots: ${OUT}`);
if (failures > 0) process.exitCode = 1;
