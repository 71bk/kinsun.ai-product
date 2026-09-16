// Local-only real login bridge. Never emit credentials or cookie values.
const { chromium } = require('playwright');
(async () => {
  let browser;
  try {
    const password = process.env.DEMO_ACCOUNT_PASSWORD;
    if (!password) throw new Error('Missing DEMO_ACCOUNT_PASSWORD in process environment');
    browser = await chromium.launch({ channel: 'chrome', headless: false,
      args: ['--remote-debugging-port=9333', '--remote-debugging-address=127.0.0.1'] });
    for (const role of ['elder', 'staff']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      await page.goto('http://localhost:3000/' + (role === 'staff' ? 'staff/sign-in' : 'elder/start') + '?qa=wave2-chain');
      await page.locator('input[name="email"]').fill(role + '.demo@kinsun.local');
      await page.locator('input[name="password"]').fill(password);
      await page.getByRole('button', { name: role === 'staff' ? '登入 / Sign in' : '登入並開始使用', exact: true }).click();
      await page.waitForURL(url => !url.pathname.includes('sign-in') && url.pathname !== '/elder/start', { timeout: 30000 });
      await page.evaluate(role => { window.name = 'wave2-chain-' + role; }, role);
      console.log(JSON.stringify({ role, login: 'passed', path: new URL(page.url()).pathname }));
    }
    await new Promise(resolve => browser.on('disconnected', resolve));
  } catch {
    console.log(JSON.stringify({ login: 'failed', detail: 'redacted' }));
    if (browser) await browser.close();
    process.exitCode = 1;
  }
})();
