// Local-only bridge: real form login, no credential or cookie output.
const { chromium } = require('playwright');

(async () => {
  let browser;
  try {
    const password = process.env.DEMO_ACCOUNT_PASSWORD;
    if (!password) throw new Error('Missing DEMO_ACCOUNT_PASSWORD in process environment');
    browser = await chromium.launch({
      channel: 'chrome', headless: false,
      args: ['--remote-debugging-port=9333', '--remote-debugging-address=127.0.0.1'],
    });
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await page.goto('http://localhost:3000/staff/sign-in');
    await page.locator('input[name="email"]').fill('staff.demo@kinsun.local');
    await page.locator('input[name="password"]').fill(password);
    await page.getByRole('button', { name: '登入 / Sign in', exact: true }).click();
    await page.waitForURL(url => !url.pathname.includes('sign-in'), { timeout: 30000 });
    console.log(JSON.stringify({ login: 'passed', path: new URL(page.url()).pathname, debugPort: 9333 }));
    await new Promise(resolve => browser.on('disconnected', resolve));
  } catch {
    console.log(JSON.stringify({ login: 'failed', detail: 'redacted; inspect safe page state' }));
    if (browser) await browser.close();
    process.exitCode = 1;
  }
})();
